#!/usr/bin/env python3
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

from metashape.gpu_setup import setup_gpu
from metashape.utils import find_images
from metashape.camera_ops import (
    configure_multispectral_camera,
    remove_images_outside_rgb_times,
    camera_filtering
)
from metashape.processing import (
    detect_reflectance_panels,
    align_images,
    build_model,
    merge_chunks
)
from metashape.resume import resume_proc

def main():
    # Set up GPU acceleration
    setup_gpu()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize Metashape project with all images in one chunk.")
    parser.add_argument('-imagery_dir', required=True, help='Path to YYYYMMDD/imagery/ directory')
    parser.add_argument('-crs', default="4326", help='EPSG code for target projected CRS (default: 4326, WGS84)')
    parser.add_argument('-out', required=True, help='Directory to save the Metashape project')
    parser.add_argument('-smooth', choices=['low', 'medium', 'high'], default='low',
                      help='Smoothing strength for the model (default: low)')
    parser.add_argument('-sun_sensor', action='store_true', default=False,
                      help='Whether to use sun sensor data for reflectance calibration (default: False)')
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

    # Camera filter - remove images from each chunk
    camera_filtering(rgb_chunk, multispec_chunk)

    # Save project after filtering
    doc.save()
    print("Project saved with filtered chunks")

    # Add resume processing menu item
    print(
        "Step 1. In the Workspace pane under multispec chunk open Calibration images folder. Select and remove images not to be used for calibration.")
    print(
        "Step 2. Press the 'Show Masks' icon in the toolbar and inspect the masks on calibration images.")
    print(
        "Step 3. Select in top menu Tools > Calibrate Reflectance > Use 1 to 5 images for calibration.")
    print(
        "Step 4. Ensure there's a csv file of the calibration panel loaded.  Press Cancel.")
    print(
        "Note: The csv of the calibration panel will have to be loaded if this is the first run on the machine. See the protocol for more information.")

    print(
        "Complete Steps 1 to 4 and press 'Resume Processing' to continue. Reflectance calibration will be completed in the script.")
    print("###########################")
    print("###########################")

    # Add resume processing menu item
    label = "Resume processing"
    Metashape.app.removeMenuItem(label)
    Metashape.app.addMenuItem(label, lambda: resume_proc(doc, multispec_chunk, args))
    Metashape.app.messageBox(
        "Complete Steps 1 to 4 listed on the Console tab and then click on 'Resume Processing' in the toolbar")

if __name__ == "__main__":
    main()