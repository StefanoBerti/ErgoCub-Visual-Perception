# ErgoCub-Visual-Perception
## Environment
- [Cuda 11.4.4](https://developer.nvidia.com/cuda-11-4-4-download-archive?target_os=Windows&target_arch=x86_64&target_version=10&target_type=exe_local) (filename `cuda_11.4.4_472.50_windows.exe`, fourth update)
- [CUDNN 8.2.1](https://developer.nvidia.com/compute/machine-learning/cudnn/secure/8.2.1.32/11.3_06072021/cudnn-11.3-windows-x64-v8.2.1.32.zip) (filename `cudnn-11.3-windows-x64-v8.2.1.32.zip`)
- [TensorRT 8.2.3.0](https://developer.nvidia.com/compute/machine-learning/tensorrt/secure/8.2.3.0/zip/TensorRT-8.2.3.0.Windows10.x86_64.cuda-11.4.cudnn8.2.zip) (filename `TensorRT-8.2.3.0.Windows10.x86_64.cuda-11.4.cudnn8.2.zip`, second update)

## Set up wsl
Note: for this step, you need Windows 11 or the latest update of Windows 10.
Check if your wsl have GPU driver installed by running `wsl nvidia-smi` and check the output.
Next, run wsl and type the following commands:
- wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
- bash Miniconda3-latest-Linux-x86_64.sh
- rm Miniconda3-latest-Linux-x86_64.sh
- conda create -n rapids-22.04 -c rapidsai -c nvidia -c conda-forge cuml=22.04 python=3.8 cudatoolkit=11.5

## Run
To run everything, you need to launch together `source.py`, `manager.py`, `grasping/grasping_process.py` and `human/main.py`.
To activate the debug mode, launch `gui/visualizer.py` and press `d` on the source window.