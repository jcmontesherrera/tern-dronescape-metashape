import Metashape

def setup_gpu():
    """
    Sets up GPU acceleration in Metashape by:
    1. Enabling GPU acceleration
    2. Verifying available GPUs
    3. Specifically using GPU 1 (NVIDIA) and ignoring GPU 0 (Intel)
    4. Disabling CPU usage when GPU is active
    """
    print("Setting up GPU acceleration...")
    
    # Enable GPU acceleration and disable CPU usage
    Metashape.app.gpu_mask = 2 ** 32 - 1  # Enable all available GPUs
    Metashape.app.cpu_enable = False  # Disable CPU usage when GPU is active
    
    # Get list of available GPUs
    gpu_list = Metashape.app.enumGPUDevices()
    
    if not gpu_list:
        print("Warning: No GPU devices found. Processing will use CPU only.")
        Metashape.app.cpu_enable = True  # Enable CPU since no GPU is available
        return
    
    print(f"Found {len(gpu_list)} GPU device(s):")
    for i, gpu in enumerate(gpu_list):
        print(f"GPU {i}: {gpu}")  # GPU object string representation
    
    # Directly target GPU 1 (NVIDIA) and ignore GPU 0 (Intel)
    if len(gpu_list) > 1:
        print(f"Using NVIDIA GPU (GPU 1): {gpu_list[1]}")
        # Enable only GPU 1 (NVIDIA)
        Metashape.app.gpu_mask = 1 << 1
    else:
        print("Warning: Only one GPU found. Using all available GPUs.")
    
    print("GPU setup complete.") 