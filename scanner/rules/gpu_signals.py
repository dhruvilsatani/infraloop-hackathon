# Packages that specifically imply a GPU is needed to run or train something --
# distinct from general "ai_ml" packages like openai/anthropic, which are just API
# calls and need no GPU at all on your side.

GPU_INDICATOR_PACKAGES = {
    "torch",
    "tensorflow",
    "jax",
    "transformers",
    "pytorch-lightning",
    "torchvision",
    "cupy",
    "onnxruntime-gpu",
    "vllm",
    "bitsandbytes",
    "diffusers",
    "accelerate",
    "tensorflow-gpu",
}


def detect_gpu_signals(dependency_names):
    """Given a list of lowercase dependency names, flags whether a GPU is likely needed."""
    found = [name for name in dependency_names if name in GPU_INDICATOR_PACKAGES]
    return {
        "gpu_likely": len(found) > 0,
        "frameworks_found": found,
    }
