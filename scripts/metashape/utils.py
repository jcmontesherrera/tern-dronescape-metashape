import os

def find_images(folder, extensions=(".jpg", ".jpeg", ".tif", ".tiff")):
    """
    Helper function to recursively find image files with given extensions.
    
    Args:
        folder: Path to search for images
        extensions: Tuple of allowed file extensions
        
    Returns:
        List of image file paths
    """
    image_list = []
    for root, _, files in os.walk(folder):
        for fname in files:
            if fname.lower().endswith(extensions):
                image_list.append(os.path.join(root, fname))
    return image_list

# Constants
DICT_SMOOTH_STRENGTH = {
    'low': 50,      # For low-lying vegetation (grasslands, shrublands)
    'medium': 100,  # For mixed vegetation
    'high': 200     # For forested sites
} 