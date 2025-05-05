    # Build orthomosaics
    print("Building orthomosaics...")
    # rgb_chunk.buildOrthomosaic(surface_data=Metashape.DataSource.ModelData, refine_seamlines=True)
    # doc.save()
    multispec_chunk.buildOrthomosaic(surface_data=Metashape.DataSource.ModelData, refine_seamlines=True)
    doc.save()

    # # Round resolution to 2 decimal places
    # rgb_res_xy = round(rgb_chunk.orthomosaic.resolution, 2)
    # multispec_res_xy = round(multispec_chunk.orthomosaic.resolution, 2)

    # # Define output path for RGB orthomosaic
    # # Example output path: 
    # # /path/to/imagery_dir/rgb/level1_proc/20250415_PLOTID_rgb_ortho_02.tif
    # rgb_dir = Path(imagery_dir) / "rgb" / "level1_proc"
    # rgb_ortho_path = rgb_dir / f"{yyyymmdd}_{plot}_rgb_ortho_{res_xy.split('.')[1]}.tif"

    # # Create output directory if it doesn't exist
    # rgb_dir.mkdir(parents=True, exist_ok=True)

    # compression = Metashape.ImageCompression()
    # compression.tiff_compression = Metashape.ImageCompression.TiffCompressionLZW  # Should be NONE? default on Metashape
    # compression.tiff_big = True
    # compression.tiff_tiled = True
    # compression.tiff_overviews = True

    # # Export orthomosaic
    # rgb_chunk.exportOrthomosaic(path=str(rgb_ortho_path), resolution_x=rgb_res_xy, resolution_y=rgb_res_xy,
    #                        image_format=Metashape.ImageFormatTIFF, save_alpha=False, 
    #                        source_data=Metashape.OrthomosaicData, image_compression=compression)
    # print(f"RGB orthomosaic saved to: {rgb_ortho_path}")

    # multispec_chunk.exportRaster(path=str(ortho_file), resolution_x=multispec_res_xy, 
    #                     resolution_y=multispec_res_xy, image_format=Metashape.ImageFormatTIFF,
    #                     raster_transform=Metashape.RasterTransformValue, save_alpha=False, 
    #                     source_data=Metashape.OrthomosaicData, image_compression=compression)
    # print(f"Multispectral orthomosaic saved to: {multispec_ortho_path}")


def export_orthomosaics(multispec_chunk, imagery_dir, yyyymmdd, plot, res_xy):
    """
    Export orthomosaics with proper settings.
    
    Args:
        multispec_chunk: Metashape chunk containing multispectral data
        imagery_dir: Base directory for imagery
        yyyymmdd: Date string in YYYYMMDD format
        plot: Plot identifier
        res_xy: Resolution string
    """
    # Round resolution to 2 decimal places
    multispec_res_xy = round(multispec_chunk.orthomosaic.resolution, 2)

    # Define output path for multispectral orthomosaic
    multispec_dir = Path(imagery_dir) / "multispec" / "level1_proc"
    multispec_ortho_path = multispec_dir / f"{yyyymmdd}_{plot}_multispec_ortho_{res_xy.split('.')[1]}.tif"

    # Create output directory if it doesn't exist
    multispec_dir.mkdir(parents=True, exist_ok=True)

    compression = Metashape.ImageCompression()
    compression.tiff_compression = Metashape.ImageCompression.TiffCompressionLZW
    compression.tiff_big = True
    compression.tiff_tiled = True
    compression.tiff_overviews = True

    multispec_chunk.exportRaster(path=str(multispec_ortho_path), resolution_x=multispec_res_xy, 
                        resolution_y=multispec_res_xy, image_format=Metashape.ImageFormatTIFF,
                        raster_transform=Metashape.RasterTransformValue, save_alpha=False, 
                        source_data=Metashape.OrthomosaicData, image_compression=compression)
    print(f"Multispectral orthomosaic saved to: {multispec_ortho_path}")

def build_rgb_orthomosaic(rgb_chunk, doc):
    """
    Build orthomosaics for the RGB chunk.
    
    Args:
        rgb_chunk: Metashape chunk containing RGB data
        doc: Metashape document
    """
    print("Building RGB orthomosaic...")
    rgb_chunk.buildOrthomosaic(surface_data=Metashape.DataSource.ModelData, refine_seamlines=True)
    doc.save()

def build_multispec_orthomosaic(multispec_chunk, doc):
    """
    Build orthomosaics for the multispectral chunk.
    
    Args:
        multispec_chunk: Metashape chunk containing multispectral data
        doc: Metashape document
    """
    print("Building multispectral orthomosaic...")
    multispec_chunk.buildOrthomosaic(surface_data=Metashape.DataSource.ModelData, refine_seamlines=True)
    doc.save()

def export_rgb_orthomosaic(rgb_chunk, imagery_dir, yyyymmdd, plot):
    """
    Export RGB orthomosaic with proper settings.
    
    Args:
        rgb_chunk: Metashape chunk containing RGB data
        imagery_dir: Base directory for imagery
        yyyymmdd: Date string in YYYYMMDD format
        plot: Plot identifier
    """
    # Round resolution to 2 decimal places
    rgb_res_xy = round(rgb_chunk.orthomosaic.resolution, 2)

    # Define output path for RGB orthomosaic
    rgb_dir = Path(imagery_dir) / "rgb" / "level1_proc"
    rgb_ortho_path = rgb_dir / f"{yyyymmdd}_{plot}_rgb_ortho_{str(rgb_res_xy).split('.')[1]}.tif"

    # Create output directory if it doesn't exist
    rgb_dir.mkdir(parents=True, exist_ok=True)

    compression = Metashape.ImageCompression()
    compression.tiff_compression = Metashape.ImageCompression.TiffCompressionLZW
    compression.tiff_big = True
    compression.tiff_tiled = True
    compression.tiff_overviews = True

    rgb_chunk.exportOrthomosaic(path=str(rgb_ortho_path), resolution_x=rgb_res_xy, resolution_y=rgb_res_xy,
                           image_format=Metashape.ImageFormatTIFF, save_alpha=False, 
                           source_data=Metashape.OrthomosaicData, image_compression=compression)
    print(f"RGB orthomosaic saved to: {rgb_ortho_path}")

def export_multispec_orthomosaic(multispec_chunk, imagery_dir, yyyymmdd, plot):
    """
    Export multispectral orthomosaic with proper settings.
    
    Args:
        multispec_chunk: Metashape chunk containing multispectral data
        imagery_dir: Base directory for imagery
        yyyymmdd: Date string in YYYYMMDD format
        plot: Plot identifier
    """
    # Round resolution to 2 decimal places
    multispec_res_xy = round(multispec_chunk.orthomosaic.resolution, 2)

    # Define output path for multispectral orthomosaic
    multispec_dir = Path(imagery_dir) / "multispec" / "level1_proc"
    multispec_ortho_path = multispec_dir / f"{yyyymmdd}_{plot}_multispec_ortho_{str(multispec_res_xy).split('.')[1]}.tif"

    # Create output directory if it doesn't exist
    multispec_dir.mkdir(parents=True, exist_ok=True)

    compression = Metashape.ImageCompression()
    compression.tiff_compression = Metashape.ImageCompression.TiffCompressionLZW
    compression.tiff_big = True
    compression.tiff_tiled = True
    compression.tiff_overviews = True

    multispec_chunk.exportRaster(path=str(multispec_ortho_path), resolution_x=multispec_res_xy, 
                        resolution_y=multispec_res_xy, image_format=Metashape.ImageFormatTIFF,
                        raster_transform=Metashape.RasterTransformValue, save_alpha=False, 
                        source_data=Metashape.OrthomosaicData, image_compression=compression)
    print(f"Multispectral orthomosaic saved to: {multispec_ortho_path}")

    export_rgb_orthomosaic(rgb_chunk, imagery_dir, yyyymmdd, plot)
    export_multispec_orthomosaic(multispec_chunk, imagery_dir, yyyymmdd, plot)