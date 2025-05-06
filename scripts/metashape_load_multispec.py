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
from pathlib import Path
import Metashape

from metashape.gpu_setup import setup_gpu
from metashape.utils import find_images
from metashape.camera_ops import configure_multispectral_camera
from metashape.processing import detect_reflectance_panels, merge_chunks
from metashape.markers import find_marker_files, load_markers
from metashape.image_utils import find_filtered_images, filter_images_by_timestamp, filter_multispec_by_flight_pattern

def main():
    # Set up GPU acceleration
    setup_gpu()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize Metashape project with RGB and multispectral images.")
    parser.add_argument('-imagery_dir', required=True, help='Path to YYYYMMDD/imagery/ directory')
    parser.add_argument('-crs', default="4326", help='EPSG code for target projected CRS (default: 4326, WGS84)')
    parser.add_argument('-out', required=True, help='Directory to save the Metashape project')
    parser.add_argument('-time_buffer', type=int, default=43200, 
                      help='Buffer in seconds to add to RGB time window (default: 43200 seconds = 12 hours)')
    parser.add_argument('-skip_markers', action='store_true', 
                      help='Skip loading markers even if .mrk files are found')
    parser.add_argument('-filter_method', choices=['time', 'spatial', 'both'], default='spatial',
                      help='Method to filter multispectral images (default: spatial)')
    parser.add_argument('-spatial_threshold', type=float, default=0.2,
                      help='Spatial threshold for flight pattern filtering (default: 0.2)')
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
    marker_files = []
    if not args.skip_markers:
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
    if marker_files and not args.skip_markers:
        try:
            markers_loaded = load_markers(rgb_chunk, marker_files)
            if markers_loaded > 0:
                print(f"Successfully loaded {markers_loaded} markers from .mrk files")
        except Exception as e:
            print(f"Warning: Failed to load markers: {e}")
            print("Continuing without markers")

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
    # Step 2: Filter multispectral images based on chosen method
    #-------------------------------------------
    if args.filter_method == 'time':
        # Use timestamp-based filtering
        filter_images_by_timestamp(merged_chunk, time_buffer_seconds=args.time_buffer)
    elif args.filter_method == 'spatial':
        # Use spatial pattern-based filtering
        filter_multispec_by_flight_pattern(merged_chunk, spatial_threshold=args.spatial_threshold)
    elif args.filter_method == 'both':
        # Use both methods in sequence
        filter_multispec_by_flight_pattern(merged_chunk, spatial_threshold=args.spatial_threshold)
        filter_images_by_timestamp(merged_chunk, time_buffer_seconds=args.time_buffer)
    
    # Save project after filtering images
    doc.save()
    print("Filtered multispectral images based on RGB flight pattern")
    print(f"Project saved as {project_path}. Chunk CRS: EPSG::{crs_code}")
    
    print("Script completed successfully. Project is now ready for alignment.")
    print("Next steps would include:")
    print("1. Aligning images")
    print("2. Building mesh")
    print("3. Building orthomosaic")

if __name__ == "__main__":
    main()