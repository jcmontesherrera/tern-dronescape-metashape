import datetime
import Metashape

def configure_multispectral_camera(chunk):
    """
    Configures the multispectral camera bands by adjusting their layer indices:
    - Moving Panchro from index 4 to index 10
    - Adjusting all other bands accordingly
    - Provides instructions for manually setting Panchro as the master camera
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
    
    # Adjust multispectral timestamps
    adjusted_multispec_timestamps = [t - time_offset for t in multispec_timestamps]
    first_multispec_time = min(adjusted_multispec_timestamps)
    last_multispec_time = max(adjusted_multispec_timestamps)
    
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
    for camera in chunk.cameras:
        # Only calibration images are in a group. The following line is necessary to avoid NoneType error on other images
        if camera.group is not None:
            if camera.group.label == 'Calibration images':
                continue
        if camera.label in del_camera_names:
            chunk.remove(camera)

    print("Removed images outside RGB capture times")

def camera_filtering(rgb_chunk, multispec_chunk):
    """
    Filter cameras between RGB and multispectral chunks.
    """
    # Create sets for faster lookup
    rgb_cameras = {cam for cam in rgb_chunk.cameras 
                  if not (cam.group and cam.group.label == 'Calibration images')}
    multispec_cameras = {cam for cam in multispec_chunk.cameras 
                        if not (cam.group and cam.group.label == 'Calibration images')}
    
    # Identify cameras to keep in each chunk using set comprehension
    rgb_to_keep = {cam for cam in rgb_cameras if not cam.label.startswith('IMG_')}
    multispec_to_keep = {cam for cam in multispec_cameras if not cam.label.startswith('DJI_')}
    
    # Batch remove cameras
    cameras_to_remove_rgb = list(rgb_cameras - rgb_to_keep)
    cameras_to_remove_multispec = list(multispec_cameras - multispec_to_keep)
    
    print(f"Removing {len(cameras_to_remove_rgb)} multispec cameras from RGB chunk...")
    rgb_chunk.remove(cameras_to_remove_rgb)
    
    print(f"Removing {len(cameras_to_remove_multispec)} RGB cameras from multispec chunk...")
    multispec_chunk.remove(cameras_to_remove_multispec) 