import os
import Metashape

def find_marker_files(folder):
    """
    Find .mrk marker files in a directory
    
    Args:
        folder: Path to search for marker files
        
    Returns:
        List of marker file paths
    """
    marker_files = []
    for root, _, files in os.walk(folder):
        for fname in files:
            if fname.lower().endswith('.mrk'):
                marker_files.append(os.path.join(root, fname))
    return marker_files

def read_marker_file(marker_file):
    """
    Read Agisoft marker file and return markers with their coordinates.
    Handles various file formats including comma-separated and tab-delimited.
    
    Args:
        marker_file: Path to .mrk file
        
    Returns:
        Dictionary of marker names with coordinates
    """
    markers = {}
    with open(marker_file, 'r') as f:
        lines = f.readlines()
    
    for line in lines:
        # Skip comments and empty lines
        if line.strip() == '' or line.strip().startswith('#'):
            continue
        
        # Try different separators (comma, tab, whitespace)
        parts = None
        for separator in [',', '\t', None]:  # None means split on any whitespace
            parts = line.strip().split(separator)
            # If we have at least 4 parts (name, x, y, z), we're good
            if len(parts) >= 4:
                # Clean up parts (remove empty strings)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) >= 4:
                    break
        
        if not parts or len(parts) < 4:
            print(f"Warning: Could not parse line in marker file: {line}")
            continue
        
        try:
            name = parts[0]
            # Attempt to convert coordinates to float
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            markers[name] = (x, y, z)
        except (ValueError, IndexError) as e:
            print(f"Warning: Error parsing coordinates in marker file: {e}")
            continue
    
    return markers

def load_markers(chunk, mrk_files):
    """
    Load markers from .mrk files into the chunk
    
    Args:
        chunk: Metashape chunk
        mrk_files: List of .mrk file paths
        
    Returns:
        Number of markers loaded
    """
    if not mrk_files:
        print("No marker files found")
        return 0
    
    markers_loaded = 0
    print(f"Loading {len(mrk_files)} marker files")
    
    for mrk_file in mrk_files:
        try:
            markers = read_marker_file(mrk_file)
            if not markers:
                print(f"No markers found in {mrk_file}")
                continue
            
            print(f"Found {len(markers)} markers in {mrk_file}")
            
            # Add markers to the chunk
            for name, coords in markers.items():
                marker = chunk.addMarker()
                marker.label = name
                marker.reference.location = Metashape.Vector(coords)
                marker.reference.enabled = True
                markers_loaded += 1
                
        except Exception as e:
            print(f"Error loading marker file {mrk_file}: {e}")
    
    if markers_loaded > 0:
        print(f"Successfully loaded {markers_loaded} markers")
    
    return markers_loaded 