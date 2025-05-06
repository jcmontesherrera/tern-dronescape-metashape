import os
import datetime
import math
import numpy as np
import Metashape

def find_filtered_images(folder, extensions=(), exclude_patterns=()):
    """
    Helper function to recursively find image files with given extensions,
    excluding files that match any patterns in exclude_patterns.
    
    Args:
        folder: Path to search for images
        extensions: Tuple of allowed file extensions
        exclude_patterns: Tuple of patterns to exclude (file endings)
        
    Returns:
        List of image file paths that match the criteria
    """
    image_list = []
    for root, _, files in os.walk(folder):
        for fname in files:
            # Check if file has allowed extension
            if extensions and not fname.lower().endswith(extensions):
                continue
                
            # Check if file matches any exclude pattern
            should_exclude = False
            for pattern in exclude_patterns:
                if fname.endswith(pattern):
                    should_exclude = True
                    break
                    
            if not should_exclude:
                image_list.append(os.path.join(root, fname))
    return image_list

def filter_images_by_timestamp(chunk, time_buffer_seconds=43200):
    """
    Filter multispectral images based on RGB capture times 
    with a time buffer to ensure adequate overlap.
    
    Args:
        chunk: Metashape chunk containing both RGB and multispectral images
        time_buffer_seconds: Buffer in seconds to add to the RGB time window (default: 43200 seconds = 12 hours)
    """
    print("Filtering multispectral images based on RGB capture times...")
    
    # Collect RGB timestamps
    rgb_timestamps = []
    rgb_cameras = []
    
    # Collect multispectral timestamps
    ms_timestamps = []
    ms_cameras = []
    
    # Find cameras and their timestamps
    for camera in chunk.cameras:
        # Skip disabled cameras
        if not camera.enabled:
            continue
            
        # Get camera timestamp from metadata
        if not camera.photo.meta:
            continue
            
        timestamp_str = None
        if 'Exif/DateTimeOriginal' in camera.photo.meta:
            timestamp_str = camera.photo.meta['Exif/DateTimeOriginal']
        elif 'Xmp/DateTimeOriginal' in camera.photo.meta:
            timestamp_str = camera.photo.meta['Xmp/DateTimeOriginal']
            
        if not timestamp_str:
            continue
            
        try:
            # Try different timestamp formats
            try:
                dt = datetime.datetime.strptime(timestamp_str, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                # Alternative format sometimes found in image metadata
                dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S")

            # Check prefix to determine camera type
            if camera.label.startswith("DJI_"):
                rgb_timestamps.append(dt)
                rgb_cameras.append(camera)
            elif camera.label.startswith("IMG_"):
                ms_timestamps.append(dt)
                ms_cameras.append(camera)
        except ValueError:
            print(f"Could not parse timestamp for camera {camera.label}: {timestamp_str}")
    
    if not rgb_timestamps:
        print("No timestamps found for RGB cameras. Skipping filtering.")
        return
        
    if not ms_timestamps:
        print("No timestamps found for multispectral cameras. Skipping filtering.")
        return
    
    # Find min and max RGB timestamps
    min_rgb_time = min(rgb_timestamps)
    max_rgb_time = max(rgb_timestamps)
    
    # Add buffer to each end
    buffer = datetime.timedelta(seconds=time_buffer_seconds)
    min_rgb_time -= buffer
    max_rgb_time += buffer
    
    print(f"RGB capture time window: {min_rgb_time} to {max_rgb_time}")
    print(f"With {time_buffer_seconds} second buffer on each end ({time_buffer_seconds/3600:.1f} hours)")
    
    # List of multispec cameras to disable
    cameras_to_remove = []
    
    # Check each multispectral camera
    for i, camera in enumerate(ms_cameras):
        timestamp = ms_timestamps[i]
        
        # If outside RGB time window, mark for removal
        if timestamp < min_rgb_time or timestamp > max_rgb_time:
            cameras_to_remove.append(camera)
    
    # Remove cameras outside time window
    if cameras_to_remove:
        print(f"Removing {len(cameras_to_remove)} multispectral cameras outside RGB time window")
        chunk.remove(cameras_to_remove)
    else:
        print("All multispectral cameras are within the RGB time window")

def filter_multispec_by_flight_pattern(chunk, spatial_threshold=0.2, keep_ratio=0.8):
    """
    Filter multispectral images by analyzing the RGB flight pattern using both
    spatial and sequence information to determine which images should be kept.
    This approach is more robust to time differences between cameras.
    
    Args:
        chunk: Metashape chunk containing both RGB and multispectral images
        spatial_threshold: Distance threshold as fraction of total area (default: 0.2)
        keep_ratio: Minimum ratio of images to keep (default: 0.8)
    
    Returns:
        Number of multispectral images removed
    """
    print("Filtering multispectral images based on RGB flight pattern...")
    
    # 1. Separate RGB and multispectral cameras
    rgb_cameras = []
    ms_cameras = []
    
    for camera in chunk.cameras:
        # Skip disabled cameras
        if not camera.enabled:
            continue
            
        # Verify camera has reference (position) data
        if not camera.reference.location:
            continue
            
        # Group by camera type
        if camera.label.startswith("DJI_"):
            rgb_cameras.append(camera)
        elif camera.label.startswith("IMG_"):
            ms_cameras.append(camera)
    
    if not rgb_cameras:
        print("No RGB cameras found with position data. Cannot determine flight pattern.")
        return 0
        
    if not ms_cameras:
        print("No multispectral cameras found. Nothing to filter.")
        return 0
    
    print(f"Analyzing flight pattern of {len(rgb_cameras)} RGB images")
    
    # 2. Determine the main survey area from RGB cameras
    rgb_coords = []
    for camera in rgb_cameras:
        pos = camera.reference.location
        rgb_coords.append((pos.x, pos.y, pos.z))
    
    # Convert to numpy array for easier calculations
    rgb_coords = np.array(rgb_coords)
    
    # 3. Find the bounding box of the main flight area
    # Exclude outliers by using percentiles instead of min/max
    x_min, y_min, z_min = np.percentile(rgb_coords, 5, axis=0)
    x_max, y_max, z_max = np.percentile(rgb_coords, 95, axis=0)
    
    # Calculate the main area dimensions
    width = x_max - x_min
    height = y_max - y_min
    depth = z_max - z_min
    
    # Expand the bounding box by the spatial threshold
    x_min -= width * spatial_threshold
    x_max += width * spatial_threshold
    y_min -= height * spatial_threshold
    y_max += height * spatial_threshold
    z_min -= depth * spatial_threshold
    z_max += depth * spatial_threshold
    
    print(f"Main flight area: X({x_min:.2f} to {x_max:.2f}), Y({y_min:.2f} to {y_max:.2f}), Z({z_min:.2f} to {z_max:.2f})")
    
    # 4. Determine which multispectral images fall within this area
    ms_in_area = []
    ms_outside_area = []
    
    for camera in ms_cameras:
        pos = camera.reference.location
        if (x_min <= pos.x <= x_max and
            y_min <= pos.y <= y_max and
            z_min <= pos.z <= z_max):
            ms_in_area.append(camera)
        else:
            ms_outside_area.append(camera)
    
    in_area_ratio = len(ms_in_area) / len(ms_cameras)
    
    # 5. Check if we have enough images in the area
    # If too many images would be removed, the bounding box might be too restrictive
    if in_area_ratio < keep_ratio:
        print(f"Warning: Only {in_area_ratio:.2%} of multispectral images are within the main flight area.")
        print("This might indicate that the spatial filter is too restrictive.")
        print("Trying alternative approach based on altitude...")
        
        # 5b. Alternative: Filter based on altitude only
        # Calculate the mean altitude of RGB cameras
        rgb_mean_alt = np.mean(rgb_coords[:, 2])
        rgb_std_alt = np.std(rgb_coords[:, 2])
        
        # Set an altitude threshold
        alt_range = rgb_std_alt * 2  # 2 standard deviations
        alt_min = rgb_mean_alt - alt_range
        alt_max = rgb_mean_alt + alt_range
        
        print(f"RGB altitude range: {alt_min:.2f} to {alt_max:.2f} (mean: {rgb_mean_alt:.2f}, std: {rgb_std_alt:.2f})")
        
        # Re-filter based on altitude only
        ms_in_area = []
        ms_outside_area = []
        
        for camera in ms_cameras:
            pos = camera.reference.location
            if alt_min <= pos.z <= alt_max:
                ms_in_area.append(camera)
            else:
                ms_outside_area.append(camera)
        
        in_area_ratio = len(ms_in_area) / len(ms_cameras)
        print(f"After altitude filtering: {in_area_ratio:.2%} of multispectral images are within operational altitude range")
    
    # 6. Remove multispectral images outside the main area
    if ms_outside_area:
        print(f"Removing {len(ms_outside_area)} multispectral images outside the main flight area")
        chunk.remove(ms_outside_area)
    else:
        print("All multispectral images are within the main flight area")
    
    return len(ms_outside_area) 