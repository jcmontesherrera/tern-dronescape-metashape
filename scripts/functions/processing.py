import Metashape
from .utils import DICT_SMOOTH_STRENGTH

def detect_reflectance_panels(chunk):
    """
    Detects reflectance panels in multispectral images based on QR codes.
    Only processes multispectral images (.tif files).
    """
    print("Detecting reflectance panels in multispectral images...")
    chunk.locateReflectancePanels()
    print("Reflectance panel detection complete.")

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

def calibrate_reflectance_and_transform(multispec_chunk, multispec_sensors, doc, use_sun_sensor=False):
    """
    Calibrate reflectance and update raster transform for multispectral images.
    
    Args:
        multispec_chunk: Metashape chunk containing multispectral data
        multispec_sensors: List of multispectral sensors
        doc: Metashape document
        use_sun_sensor: Whether to use sun sensor data for calibration
    """
    # Calibrate reflectance 
    multispec_chunk.calibrateReflectance(use_reflectance_panels=True, use_sun_sensor=use_sun_sensor)

    # Raster transform multispectral images
    print("Updating Raster Transform for relative reflectance")
    raster_transform_formula = []
    
    # Get sensors sorted by layer_index
    sorted_sensors = sorted([sensor for sensor in multispec_sensors if sensor.layer_index < 10], 
                          key=lambda x: x.layer_index)
    
    # Create transform formula for first 10 bands only, excluding panchro
    for sensor in sorted_sensors:
        # Use the actual layer index for the band reference
        band_idx = sensor.layer_index
        raster_transform_formula.append(f"B{band_idx}/32768")

    multispec_chunk.raster_transform.formula = raster_transform_formula
    multispec_chunk.raster_transform.calibrateRange()
    multispec_chunk.raster_transform.enabled = True
    
    doc.save()
    print(f"Applied raster transform formulas: {raster_transform_formula}")

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