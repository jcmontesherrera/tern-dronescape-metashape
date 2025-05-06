#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to initialize a Metashape project with RGB and multispectral images in separate chunks.
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

from functions.gpu_setup import setup_gpu
from functions.utils import find_images
from functions.camera_ops import configure_multispectral_camera
from functions.processing import detect_reflectance_panels

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

def main():
    # Set up GPU acceleration
    setup_gpu()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize Metashape project with RGB and multispectral images.")
    parser.add_argument('-imagery_dir', required=True, help='Path to YYYYMMDD/imagery/ directory')
    parser.add_argument('-crs', default="4326", help='EPSG code for target projected CRS (default: 4326, WGS84)')
    parser.add_argument('-out', required=True, help='Directory to save the Metashape project')
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
    
    # Detect reflectance panels in multispectral chunk
    detect_reflectance_panels(multispec_chunk)

    # Set CRS for both chunks
    crs_code = args.crs
    target_crs = Metashape.CoordinateSystem(f"EPSG::{crs_code}")
    rgb_chunk.crs = target_crs
    multispec_chunk.crs = target_crs

    # Save project
    doc.save()

    print("Merging RGB and multispectral chunks...")
    merged_chunk = merge_chunks(doc, rgb_chunk, multispec_chunk, rgb_images)
    merged_chunk.label = "all_images"

    print(f"Project saved as {project_path}. Chunk CRS: EPSG::{crs_code}")
    print("Successfully loaded RGB and multispectral images into separate chunks.")
    print("Next steps would include:")
    print("2. Removing images outside RGB capture times")
    print("3. Aligning images")
    print("4. Building dense cloud and mesh")
    print("5. Building orthomosaic")

if __name__ == "__main__":
    main() 