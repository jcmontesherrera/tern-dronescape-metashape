import os
import datetime
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