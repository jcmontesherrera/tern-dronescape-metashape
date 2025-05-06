#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to initialize a Metashape project with RGB and multispectral images in separate chunks,
then merge them and prepare for alignment.
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
import datetime
import re
from pathlib import Path
import Metashape

from metashape.gpu_setup import setup_gpu
from metashape.utils import find_images
from metashape.camera_ops import configure_multispectral_camera
from metashape.processing import detect_reflectance_panels, merge_chunks

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

def filter_images_by_timestamp(chunk, time_buffer_seconds=30):
    """
    Filter multispectral images based on RGB capture times 
    with a time buffer to ensure adequate overlap.
    
    Args:
        chunk: Metashape chunk containing both RGB and multispectral images
        time_buffer_seconds: Buffer in seconds to add to the RGB time window (default: 30)
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
    print(f"With {time_buffer_seconds} second buffer on each end")
    
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

def read_marker_file(marker_file):
    """
    Read Agisoft marker file and return markers with their coordinates
    
    Args:
        marker_file: Path to .mrk file
        
    Returns:
        Dictionary of marker names with coordinates
    """
    markers = {}
    with open(marker_file, 'r') as f:
        lines = f.readlines()
        
    for line in lines:
        if line.startswith('#'):
            continue
            
        parts = line.strip().split(',')
        if len(parts) >= 4:
            name = parts[0]
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            markers[name] = (x, y, z)
    
    return markers

def find_marker_files(folder):
    """
    Find .mrk marker files in the RGB directory
    
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

def load_markers(chunk, mrk_files):
    """
    Load markers from .mrk files into the chunk
    
    Args:
        chunk: Metashape chunk
        mrk_files: List of .mrk file paths
        
    Returns:
        True if markers were loaded, False otherwise
    """
    if not mrk_files:
        print("No marker files found")
        return False
        
    print(f"Loading {len(mrk_files)} marker files")
    for mrk_file in mrk_files:
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
    
    return True

def main():
    # Set up GPU acceleration
    setup_gpu()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize Metashape project with RGB and multispectral images.")
    parser.add_argument('-imagery_dir', required=True, help='Path to YYYYMMDD/imagery/ directory')
    parser.add_argument('-crs', default="4326", help='EPSG code for target projected CRS (default: 4326, WGS84)')
    parser.add_argument('-out', required=True, help='Directory to save the Metashape project')
    parser.add_argument('-time_buffer', type=int, default=30, 
                      help='Buffer in seconds to add to RGB time window (default: 30)')
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

    # Find all RGB images (jpg files)
    rgb_images = find_filtered_images(rgb_dir, extensions=('.jpg', '.jpeg'))
    
    # Find all multispectral images (tif files), excluding Panchro images (ending with _6.tif)
    multispec_images = find_filtered_images(multispec_dir, extensions=('.tif', '.tiff'), exclude_patterns=('_6.tif',))
    
    # Find marker files in RGB directory
    marker_files = find_marker_files(rgb_dir)
    if marker_files:
        print(f"Found {len(marker_files)} marker files in {rgb_dir}")

    if not rgb_images:
        sys.exit(f"No RGB images found in {rgb_dir}")
    if not multispec_images:
        sys.exit(f"No multispectral images found in {multispec_dir}")

    print(f"Found {len(rgb_images)} RGB images")
    print(f"Found {len(multispec_images)} multispectral images (excluding Panchro band)")

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
    multispec_chunk.label = "multispec_images"

    # Add images to their respective chunks with GPU acceleration
    print(f"Adding {len(rgb_images)} RGB images to the project...")
    rgb_chunk.addPhotos(rgb_images)

    print(f"Adding {len(multispec_images)} multispectral images to the project...")
    multispec_chunk.addPhotos(multispec_images, layout=Metashape.MultiplaneLayout)

    if len(rgb_chunk.cameras) == 0:
        sys.exit("RGB chunk is empty after adding images.")
    if len(multispec_chunk.cameras) == 0:
        sys.exit("Multispectral chunk is empty after adding images.")

    # Configure multispectral camera band indices
    configure_multispectral_camera(multispec_chunk)
    
    # Load markers if available
    if marker_files:
        load_markers(rgb_chunk, marker_files)

    # Detect reflectance panels in multispectral chunk
    detect_reflectance_panels(multispec_chunk)

    # Set CRS for both chunks
    crs_code = args.crs
    target_crs = Metashape.CoordinateSystem(f"EPSG::{crs_code}")
    rgb_chunk.crs = target_crs
    multispec_chunk.crs = target_crs

    # Save project before merging
    doc.save()
    print(f"Project saved with separate RGB and multispectral chunks. Project path: {project_path}")
    
    #-------------------------------------------
    # Step 1: Merge chunks into one (RGB into multispec)
    #-------------------------------------------
    print("Merging RGB and multispectral chunks...")
    merged_chunk = merge_chunks(doc, rgb_chunk, multispec_chunk, rgb_images)
    merged_chunk.label = "all_images"
    
    # Save project after merging
    doc.save()
    print("Chunks merged successfully into 'all_images' chunk")
    
    #-------------------------------------------
    # Step 2: Filter multispectral images based on RGB capture times
    #-------------------------------------------
    filter_images_by_timestamp(merged_chunk, time_buffer_seconds=args.time_buffer)
    
    # Save project after filtering images
    doc.save()
    print("Filtered multispectral images based on RGB capture times")
    print(f"Project saved as {project_path}. Chunk CRS: EPSG::{crs_code}")
    
    print("Script completed successfully. Project is now ready for alignment.")
    print("Next steps would include:")
    print("1. Aligning images")
    print("2. Building mesh")
    print("3. Building orthomosaic")

if __name__ == "__main__":
    main() 