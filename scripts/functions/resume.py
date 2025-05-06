import Metashape
from .processing import calibrate_reflectance_and_transform

def resume_proc(doc, multispec_chunk, args):
    """Resume processing after manual steps are completed.
    
    Args:
        doc: Metashape document
        multispec_chunk: Multispectral chunk to process
        args: Script arguments containing processing parameters
    """
    if not multispec_chunk:
        raise ValueError("Multispectral chunk not found")
    
    multispec_sensors = multispec_chunk.sensors
    
    # Execute the processing steps
    calibrate_reflectance_and_transform(multispec_chunk, multispec_sensors, doc, args.sun_sensor)
    
    print("Processing completed successfully!") 