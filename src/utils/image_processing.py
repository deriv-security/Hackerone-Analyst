"""
Image processing utilities for Hai.
"""

import requests
import tempfile
import os
from PIL import Image
from io import BytesIO
from ..utils.logging import log_error

def remove_transparency(image_url: str) -> str:
    """
    Download an image from a URL, remove transparent background, and save to a temporary file.
    
    Args:
        image_url: URL of the image
        
    Returns:
        str: Path to the processed image file
    """
    try:
        # Download the image
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        
        # Create a temporary file
        temp_image_fd, temp_image_path = tempfile.mkstemp(suffix='.png')
        os.close(temp_image_fd)  # Close the file descriptor
        
        # Save the original image to the temporary file
        with open(temp_image_path, 'wb') as f:
            f.write(response.content)
        
        # Remove transparency
        img = Image.open(temp_image_path)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            # Create new image with white background
            background = Image.new('RGBA', img.size, (255, 255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            # Composite the image onto the background
            img = Image.alpha_composite(background, img)
            # Convert back to RGB (no alpha)
            img = img.convert('RGB')
            # Save the modified image
            img.save(temp_image_path, 'PNG')
        
        return temp_image_path
        
    except Exception as e:
        log_error(e, "Error processing image")
        # Return None if processing fails
        return None
