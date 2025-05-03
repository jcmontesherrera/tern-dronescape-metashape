# -*- coding: utf-8 -*-
"""
Script to initialize a Metashape project with all RGB and multispec images in a single chunk.
Assumes TERN directory structure:
    <plot>/YYYYMMDD/imagery/
        ├── rgb/level0_raw/
        └── multispec/level0_raw/
User provides:
    --imagery_dir: path to YYYYMMDD/imagery/
    --crs: EPSG code for target CRS (optional, defaults to 4326)
    --out: output directory for Metashape project
Project will be named as "YYYYMMDD-plot.psx"
"""

import argparse
import os
import sys
from pathlib import Path
import Metashape
import datetime

# Add this near the top with other constants
DICT_SMOOTH_STRENGTH = {
    'low': 50,      # For low-lying vegetation (grasslands, shrublands)
    'medium': 100,  # For mixed vegetation
    'high': 200     # For forested sites
}

# Helper function to recursively find image files with given extensions
def find_images(folder, extensions=(".jpg", ".jpeg", ".tif", ".tiff")):
    image_list = []
    for root, _, files in os.walk(folder):
        for fname in files:
            if fname.lower().endswith(extensions):
                image_list.append(os.path.join(root, fname))
    return image_list

# Reorders multispectral camera bands to match TERN's band order specification
# Moves Panchro band to index 10 and adjusts other bands accordingly
def configure_multispectral_camera(chunk):
    """
    Configures the multispectral camera bands by adjusting their layer indices:
    - Moving Panchro from index 4 to index 10
    - Adjusting all other bands accordingly
    - Provides instructions for manually setting Panchro as the master camera
    The band order will be:
    0. Coastal [444 nm]
    1. Blue [475 nm]
    2. Green [531 nm]
    3. Green [560 nm]
    4. Red [650 nm] (was 5)
    5. Red [668 nm] (was 6)
    6. RedEdge [705 nm] (was 7)
    7. RedEdge [717 nm] (was 8)
    8. NIR [740 nm] (was 9)
    9. NIR [842 nm] (was 10)
    10. Panchro (was 4)
    """
    print("Configuring multispectral camera band indices...")
    
    # Store sensor mappings for reordering
    sensors_by_name = {}
    for sensor in chunk.sensors:
        # Skip sensors without layer index (like RGB camera)
        if not hasattr(sensor, 'layer_index'):
            continue
        sensors_by_name[sensor.label] = sensor
    
    # Get all multispectral sensors
    multispec_sensors = [s for s in chunk.sensors if hasattr(s, 'layer_index')]
    
    # If no multispectral sensors found, return
    if not multispec_sensors:
        print("No multispectral sensors found. Skipping configuration.")
        return
    
    # Find the Panchro sensor
    panchro_sensor = None
    for sensor in multispec_sensors:
        if "Panchro" in sensor.label:
            panchro_sensor = sensor
            break
    
    if not panchro_sensor:
        print("Warning: Panchro sensor not found. Cannot reconfigure multispectral camera.")
        return
    
    original_panchro_index = panchro_sensor.layer_index
    print(f"Found Panchro sensor at layer index {original_panchro_index}")
    
    # Create mapping of current indices to new indices
    index_mapping = {}
    
    # All bands after Panchro need to have their index reduced by 1
    for sensor in multispec_sensors:
        current_index = sensor.layer_index
        
        if "Panchro" in sensor.label:
            # Move Panchro to index 10
            index_mapping[current_index] = 10
        elif current_index > original_panchro_index:
            # Shift indices down for bands after Panchro
            index_mapping[current_index] = current_index - 1
        else:
            # Keep indices the same for bands before Panchro
            index_mapping[current_index] = current_index
    
    # Apply the new layer indices
    # We need to create temporary assignments to avoid conflicts
    # First, assign all to high temporary indices to avoid conflicts
    temp_offset = 100
    for sensor in multispec_sensors:
        current_index = sensor.layer_index
        sensor.layer_index = index_mapping[current_index] + temp_offset
    
    # Then assign to the final indices
    for sensor in multispec_sensors:
        temp_index = sensor.layer_index
        sensor.layer_index = temp_index - temp_offset
        print(f"Set {sensor.label} to layer index {sensor.layer_index}")
    
    # Find the Panchro sensor/camera for reference in manual instruction
    panchro_camera_name = "Not found"
    for camera in chunk.cameras:
        if camera.sensor == panchro_sensor:
            panchro_camera_name = camera.label
            break
    
    # Set Panchro as the master camera
    panchro_sensor.makeMaster()
    print(f"Set {panchro_sensor.label} as master camera")

# Detects reflectance panels in multispectral images using QR codes
def detect_reflectance_panels(chunk):
    """
    Detects reflectance panels in multispectral images based on QR codes.
    Only processes multispectral images (.tif files).
    """
    print("Detecting reflectance panels in multispectral images...")
    
    # Enable GPU acceleration for panel detection
    Metashape.app.gpu_mask = 2 ** 32 - 1
    chunk.locateReflectancePanels()
    print("Reflectance panel detection complete.")

# Merges RGB chunk into multispectral chunk and removes the RGB chunk
# Preserves multispectral chunk as it contains calibration settings
def merge_chunks(doc, rgb_chunk, multispec_chunk, rgb_images):
    """
    Merges the RGB chunk into the multispectral chunk and removes the RGB chunk.
    The multispectral chunk is preserved as it contains calibration settings and panel detection.
    """
    print("Merging chunks...")
    
    # Add all RGB images to multispectral chunk at once
    print(f"Adding {len(rgb_images)} RGB images to multispectral chunk...")
    multispec_chunk.addPhotos(rgb_images)
    
    # Add RGB sensor to multispectral chunk
    for sensor in rgb_chunk.sensors:
        # Create a new sensor in multispec chunk with the same settings
        new_sensor = multispec_chunk.addSensor()
        new_sensor.label = sensor.label
        new_sensor.type = sensor.type
        new_sensor.width = sensor.width
        new_sensor.height = sensor.height
        new_sensor.pixel_size = sensor.pixel_size
        new_sensor.focal_length = sensor.focal_length
        new_sensor.fixed = sensor.fixed
        new_sensor.antenna.location_ref = sensor.antenna.location_ref
    
    # Remove the RGB chunk
    doc.remove(rgb_chunk)
    
    print("Chunks merged successfully.")
    return multispec_chunk

def remove_images_outside_rgb_times(chunk):
    """
    Removes multispectral images that were captured outside of RGB camera capture times.
    Uses filename prefixes to identify RGB ('DJI_') and multispectral ('IMG_') cameras.
    Automatically detects and adjusts for time offset between cameras.
    """
    print("Removing images outside RGB capture times...")
    
    # Maximum allowed time offset in hours (to avoid matching wrong days)
    MAX_OFFSET_HOURS = 6
    
    def get_camera_timestamps(prefix):
        """Helper function to get timestamps for cameras with given prefix"""
        timestamps = []
        for camera in chunk.cameras:
            if not camera.label.startswith(prefix):
                continue
            if not camera.label == camera.master.label:
                continue
            if not camera.photo.meta:
                continue
                
            if 'Exif/DateTimeOriginal' in camera.photo.meta:
                timestamp = camera.photo.meta['Exif/DateTimeOriginal']
                try:
                    dt = datetime.datetime.strptime(timestamp, "%Y:%m:%d %H:%M:%S")
                    # If hour is less than 12, assume it's PM (add 12 hours)
                    if dt.hour < 12:
                        dt = dt.replace(hour=dt.hour + 12)
                    timestamps.append(dt.timestamp())
                except ValueError as e:
                    print(f"Error parsing timestamp for {camera.label}: {e}")
        return timestamps
    
    # Get RGB camera timestamps
    rgb_timestamps = get_camera_timestamps('DJI_')
    if not rgb_timestamps:
        print("Could not get RGB camera timestamps")
        return
        
    # Get actual capture times
    first_rgb_time = min(rgb_timestamps)
    last_rgb_time = max(rgb_timestamps)
    
    # print(f"\nRGB capture times:")
    # print(f"First image: {datetime.datetime.fromtimestamp(first_rgb_time)}")
    # print(f"Last image:  {datetime.datetime.fromtimestamp(last_rgb_time)}")
    
    # Get multispectral camera timestamps
    multispec_timestamps = get_camera_timestamps('IMG_')
    if not multispec_timestamps:
        print("Could not get multispectral camera timestamps")
        return
        
    # Calculate the center points of both capture windows
    rgb_center = (first_rgb_time + last_rgb_time) / 2
    multispec_center = (min(multispec_timestamps) + max(multispec_timestamps)) / 2
    
    # Calculate potential offset in hours
    raw_offset_hours = (multispec_center - rgb_center) / 3600
    
    # Find the closest reasonable offset (within MAX_OFFSET_HOURS)
    if abs(raw_offset_hours) > MAX_OFFSET_HOURS:
        # If the raw offset is too large, try to find the closest reasonable offset
        # by checking offsets in 1-hour increments
        best_offset = 0
        min_diff = float('inf')
        for offset in range(-MAX_OFFSET_HOURS, MAX_OFFSET_HOURS + 1):
            adjusted_center = multispec_center - (offset * 3600)
            diff = abs(adjusted_center - rgb_center)
            if diff < min_diff:
                min_diff = diff
                best_offset = offset
        time_offset = best_offset * 3600
    else:
        # Round to nearest hour if within reasonable range
        time_offset = round(raw_offset_hours) * 3600
    
    # print(f"\nDetected time offset: {time_offset/3600:.1f} hours")
    
    # Adjust multispectral timestamps
    adjusted_multispec_timestamps = [t - time_offset for t in multispec_timestamps]
    first_multispec_time = min(adjusted_multispec_timestamps)
    last_multispec_time = max(adjusted_multispec_timestamps)
    
    # print(f"\nMultispec capture times (after {time_offset/3600:.1f} hour adjustment):")
    # print(f"First image: {datetime.datetime.fromtimestamp(first_multispec_time)}")
    # print(f"Last image:  {datetime.datetime.fromtimestamp(last_multispec_time)}")
    
    # Create a list of cameras with Altitude = 0
    del_camera_names = list()

    # Check multispectral cameras
    for camera in chunk.cameras:
        if not camera.label.startswith('IMG_'):
            continue
        if not camera.label == camera.master.label:
            continue
        if not camera.photo.meta:
            continue
            
        if 'Exif/DateTimeOriginal' in camera.photo.meta:
            timestamp = camera.photo.meta['Exif/DateTimeOriginal']
            print(f"\nMultispec camera {camera.label} timestamp: {timestamp}")
            try:
                # Parse the timestamp
                dt = datetime.datetime.strptime(timestamp, "%Y:%m:%d %H:%M:%S")
                # If hour is less than 12, assume it's PM (add 12 hours)
                if dt.hour < 12:
                    dt = dt.replace(hour=dt.hour + 12)
                # Apply the detected time offset
                cam_time = dt.timestamp() - time_offset
                # print(f"Adjusted timestamp: {datetime.datetime.fromtimestamp(cam_time)}")
                # print(f"Time difference from RGB start: {(cam_time - first_rgb_time)/3600:.2f} hours")
                # print(f"Time difference from RGB end: {(cam_time - last_rgb_time)/3600:.2f} hours")
                
                # If outside RGB capture window, set altitude=0
                if cam_time < first_rgb_time or cam_time > last_rgb_time:
                    if camera.reference.location:
                        new_loc = Metashape.Vector((camera.reference.location.x, 
                                                  camera.reference.location.y, 
                                                  0))  # Set altitude to 0
                        camera.reference.location = new_loc
                        del_camera_names.append(camera.label)
                        print(f"Marked camera {camera.label} for deletion (outside RGB capture window)")
            except ValueError as e:
                print(f"Error parsing timestamp for {camera.label}: {e}")

    # Delete images outside of RGB capture times
    # print(f"\nFound {len(del_camera_names)} images outside RGB capture times")
    for camera in chunk.cameras:
        # Only calibration images are in a group. The following line is necessary to avoid NoneType error on other images
        if camera.group is not None:
            if camera.group.label == 'Calibration images':
                continue
        if camera.label in del_camera_names:
            chunk.remove(camera)
            # print(f"Removed camera {camera.label}")

    print("Removed images outside RGB capture times")

def align_images(chunk):
    """
    Align images with specified settings:
    - Accuracy: High
    - Generic Preselection: Enabled
    - Reference Preselection: Source
    - Key Points: 50,000
    - Tie Points: 5,000
    - Exclude stationary points: Enabled
    - Guided Image Matching: Disabled
    """
    print("Aligning images...")
    
    # Match photos with specified settings
    chunk.matchPhotos(
        downscale=1,  # High accuracy
        generic_preselection=True,  # Enable generic preselection
        reference_preselection=True,  # Enable reference preselection
        reference_preselection_mode=Metashape.ReferencePreselectionSource,  # Source mode
        keypoint_limit=50000,  # Key points limit
        tiepoint_limit=5000,  # Tie points limit
        filter_stationary_points=True,  # Exclude stationary points
        guided_matching=False,  # Disable guided image matching,
    )
    
    # Align cameras
    chunk.alignCameras()
    
    # Optimize cameras with specified parameters
    chunk.optimizeCameras(
        fit_f=True,  # Fit focal length
        fit_cx=True,  # Fit principal point x
        fit_cy=True,  # Fit principal point y
        fit_k1=True,  # Fit radial distortion k1
        fit_k2=True,  # Fit radial distortion k2
        fit_k3=True,  # Fit radial distortion k3
        fit_p1=True,  # Fit tangential distortion p1
        fit_p2=True,  # Fit tangential distortion p2
        fit_b1=True,  # Fit affinity b1
        fit_b2=True,  # Fit affinity b2
        fit_corrections=True,  # Fit additional corrections
    )
    
    print("Image alignment complete!")

def build_model(chunk, smooth_strength='low'):
    """
    Build and optimize model using tie points data.
    This is more efficient and sufficient for orthomosaic generation.
    
    Args:
        chunk: Metashape chunk containing the aligned images
        smooth_strength: Smoothing strength ('low', 'medium', or 'high')
    """
    print("Building model from tie points...")
    
    # Build the model
    chunk.buildModel(
        surface_type=Metashape.HeightField,
        source_data=Metashape.TiePointsData,
        face_count=Metashape.MediumFaceCount,
        interpolation=Metashape.EnabledInterpolation,
        build_texture=False
    )
    
    # Smooth model based on specified strength
    print(f"Smoothing model with {smooth_strength} strength...")
    smooth_val = DICT_SMOOTH_STRENGTH[smooth_strength]
    chunk.smoothModel(smooth_val, fix_borders=True)
    
    print("Model building and smoothing complete!")

def setup_gpu():
    """
    Sets up GPU acceleration in Metashape by:
    1. Enabling GPU acceleration
    2. Verifying available GPUs
    3. Specifically using GPU 1 (NVIDIA) and ignoring GPU 0 (Intel)
    4. Disabling CPU usage when GPU is active
    """
    print("Setting up GPU acceleration...")
    
    # Enable GPU acceleration and disable CPU usage
    Metashape.app.gpu_mask = 2 ** 32 - 1  # Enable all available GPUs
    Metashape.app.cpu_enable = False  # Disable CPU usage when GPU is active
    
    # Get list of available GPUs
    gpu_list = Metashape.app.enumGPUDevices()
    
    if not gpu_list:
        print("Warning: No GPU devices found. Processing will use CPU only.")
        Metashape.app.cpu_enable = True  # Enable CPU since no GPU is available
        return
    
    print(f"Found {len(gpu_list)} GPU device(s):")
    for i, gpu in enumerate(gpu_list):
        print(f"GPU {i}: {gpu}")  # GPU object string representation
    
    # Directly target GPU 1 (NVIDIA) and ignore GPU 0 (Intel)
    if len(gpu_list) > 1:
        print(f"Using NVIDIA GPU (GPU 1): {gpu_list[1]}")
        # Enable only GPU 1 (NVIDIA)
        Metashape.app.gpu_mask = 1 << 1
    else:
        print("Warning: Only one GPU found. Using all available GPUs.")
    
    print("GPU setup complete.")

def main():
    # Set up GPU acceleration
    setup_gpu()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize Metashape project with all images in one chunk.")
    parser.add_argument('--imagery_dir', required=True, help='Path to YYYYMMDD/imagery/ directory')
    parser.add_argument('--crs', default="4326", help='EPSG code for target projected CRS (default: 4326, WGS84)')
    parser.add_argument('--out', required=True, help='Directory to save the Metashape project')
    parser.add_argument('--smooth', choices=['low', 'medium', 'high'], default='low',
                      help='Smoothing strength for the model (default: low)')
    args = parser.parse_args()

    # Extract YYYYMMDD and plot from input path
    imagery_dir = Path(args.imagery_dir).resolve()
    if imagery_dir.name != "imagery":
        sys.exit("The --imagery_dir must point to the 'imagery' directory (e.g., <plot>/YYYYMMDD/imagery/)")
    yyyymmdd = imagery_dir.parent.name
    plot = imagery_dir.parent.parent.name
    project_name = f"{yyyymmdd}-{plot}.psx"

    # Set up paths for RGB and multispectral imagery
    rgb_dir = imagery_dir / "rgb" / "level0_raw"
    multispec_dir = imagery_dir / "multispec" / "level0_raw"

    if not rgb_dir.is_dir():
        sys.exit(f"RGB directory not found: {rgb_dir}")
    if not multispec_dir.is_dir():
        sys.exit(f"Multispec directory not found: {multispec_dir}")

    # Find all image files in both directories
    rgb_images = find_images(rgb_dir)
    multispec_images = find_images(multispec_dir)

    if not rgb_images:
        sys.exit(f"No RGB images found in {rgb_dir}")
    if not multispec_images:
        sys.exit(f"No multispectral images found in {multispec_dir}")

    # Initialize Metashape project and create output directory
    doc = Metashape.app.document
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    project_path = out_dir / project_name
    doc.save(str(project_path))

    # Remove default empty chunk if it exists
    if len(doc.chunks) == 1 and doc.chunks[0].label == "Chunk 1" and len(doc.chunks[0].cameras) == 0:
        doc.remove(doc.chunks[0])

    # Create separate chunks for RGB and multispectral images
    rgb_chunk = doc.addChunk()
    rgb_chunk.label = "rgb_images"
    
    multispec_chunk = doc.addChunk()
    multispec_chunk.label = "all_images"  # This will be our final chunk name

    # Add images to their respective chunks with GPU acceleration
    print(f"Adding {len(rgb_images)} RGB images to the project...")
    Metashape.app.gpu_mask = 2 ** 32 - 1
    rgb_chunk.addPhotos(rgb_images)

    print(f"Adding {len(multispec_images)} multispectral images to the project...")
    Metashape.app.gpu_mask = 2 ** 32 - 1
    multispec_chunk.addPhotos(multispec_images)

    if len(rgb_chunk.cameras) == 0:
        sys.exit("RGB chunk is empty after adding images.")
    if len(multispec_chunk.cameras) == 0:
        sys.exit("Multispectral chunk is empty after adding images.")

    # Configure multispectral camera band indices
    configure_multispectral_camera(multispec_chunk)
    
    # Detect reflectance panels in multispectral chunk
    detect_reflectance_panels(multispec_chunk)

    # Set CRS for both chunks
    crs_code = args.crs
    target_crs = Metashape.CoordinateSystem(f"EPSG::{crs_code}")
    rgb_chunk.crs = target_crs
    multispec_chunk.crs = target_crs

    # Merge chunks into one (RGB into multispec)
    chunk = merge_chunks(doc, rgb_chunk, multispec_chunk, rgb_images)
    doc.save()

    # Remove images outside RGB capture times
    remove_images_outside_rgb_times(chunk)
    doc.save()

    # Align and optimize images with specified settings
    align_images(chunk)
    doc.save()
    
    # Build model from tie points with specified smoothing
    build_model(chunk, smooth_strength=args.smooth)

    # Save project
    doc.save()
    print(f"Project saved as {project_path}. Chunk CRS: EPSG::{crs_code}")

    # Duplicate the 'all_images' chunk
    rgb_chunk = doc.chunk
    multispec_chunk = rgb_chunk.copy()
    rgb_chunk.label = "rgb"
    multispec_chunk.label = "multispec"
    print("Created duplicate chunk: multispec")

    # Collect cameras to remove from each chunk
    rgb_to_remove = []
    multispec_to_remove = []

    # Build lists of cameras to remove
    for camera in rgb_chunk.cameras:
        # Skip calibration images
        if camera.group is not None and camera.group.label == 'Calibration images':
            continue
        if camera.label.startswith('IMG_'):  # multispec cameras
            multispec_to_remove.append(camera)

    for camera in multispec_chunk.cameras:
        # Skip calibration images
        if camera.group is not None and camera.group.label == 'Calibration images':
            continue
        if camera.label.startswith('DJI_'):  # RGB cameras
            rgb_to_remove.append(camera)

    # Remove cameras from chunks
    print(f"Removing {len(rgb_to_remove)} multispec cameras from RGB chunk...")
    for camera in multispec_to_remove:
        rgb_chunk.remove(camera)

    print(f"Removing {len(rgb_to_remove)} RGB cameras from multispec chunk...")
    for camera in rgb_to_remove:
        multispec_chunk.remove(camera)

    # Save project after filtering
    doc.save()
    print("Project saved with filtered chunks")

if __name__ == "__main__":
    main()