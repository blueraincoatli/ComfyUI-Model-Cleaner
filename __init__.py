"""
ComfyModelCleaner - A ComfyUI plugin for cleaning unused models

This plugin helps identify and clean up unused model files in ComfyUI installations.
It analyzes workflows, custom nodes, and model usage to safely identify redundant files.

Author: ComfyUI Community
License: MIT
Version: 1.0.0
"""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Import server module to register routes
try:
    from . import model_cleaner_server
    print("ComfyModelCleaner: Server routes registered successfully")
except Exception as e:
    print(f"ComfyModelCleaner: Warning - Failed to register server routes: {e}")

# Web directory for JavaScript files
WEB_DIRECTORY = "./web"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
