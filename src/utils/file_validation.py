"""
File validation utilities for Hai Bot.
Provides comprehensive validation for all file operations.
"""

import os
import re
import uuid
from typing import List, Optional
from ..utils.logging import log_error, log_debug

def validate_file_type(file_path: str, allowed_types: Optional[List[str]] = None) -> bool:
    """
    Validate file type using magic numbers.
    
    Args:
        file_path: Path to the file to validate
        allowed_types: Optional list of allowed MIME types
        
    Returns:
        True if valid, False otherwise
    """
    try:
        import magic
    except ImportError:
        log_error(None, "python-magic package not installed. Install with: pip install python-magic")
        return False
        
    if not os.path.exists(file_path):
        log_error(None, f"File not found: {file_path}")
        return False
        
    if allowed_types is None:
        allowed_types = ["image/jpeg", "image/png", "image/gif", "application/pdf"]
    
    try:
        # Get MIME type using python-magic
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)
        
        # Check against allowed types
        if file_type not in allowed_types:
            log_error(None, f"Invalid file type: {file_type}, expected one of {allowed_types}")
            return False
        
        # Additional size validation
        file_size = os.path.getsize(file_path)
        max_size = 10 * 1024 * 1024  # 10 MB
        
        if file_size > max_size:
            log_error(None, f"File too large: {file_size} bytes, max allowed: {max_size} bytes")
            return False
            
        return True
        
    except Exception as e:
        log_error(e, f"Error validating file type: {file_path}")
        return False

def get_safe_filename(original_filename: str) -> str:
    """
    Generate a safe filename from the original.
    
    Args:
        original_filename: Original filename
        
    Returns:
        Safe filename
    """
    # Remove potentially dangerous characters
    safe_name = re.sub(r'[^\w\-\.]', '_', original_filename)
    
    # Add a UUID to prevent overwriting
    name_parts = safe_name.rsplit('.', 1)
    if len(name_parts) > 1:
        extension = name_parts[1]
        base_name = name_parts[0]
        return f"{base_name}_{uuid.uuid4().hex[:8]}.{extension}"
    else:
        return f"{safe_name}_{uuid.uuid4().hex[:8]}"

def validate_image(file_path: str) -> bool:
    """
    Validate that a file is a valid image.
    
    Args:
        file_path: Path to the image file
        
    Returns:
        True if valid, False otherwise
    """
    # Check file type
    if not validate_file_type(file_path, ["image/jpeg", "image/png", "image/gif"]):
        return False
        
    try:
        # Try to open as image to verify integrity
        from PIL import Image
        img = Image.open(file_path)
        img.verify()  # Verify it's a valid image
        
        # Check dimensions
        img = Image.open(file_path)  # Need to reopen after verify
        width, height = img.size
        
        # Reject suspiciously large or small images
        if width > 5000 or height > 5000:
            log_error(None, f"Image dimensions too large: {width}x{height}")
            return False
            
        if width < 10 or height < 10:
            log_error(None, f"Image dimensions too small: {width}x{height}")
            return False
            
        return True
        
    except Exception as e:
        log_error(e, f"Invalid image file: {file_path}")
        return False

def secure_file_path(base_dir: str, filename: str) -> str:
    """
    Create a secure file path that prevents directory traversal attacks.
    
    Args:
        base_dir: Base directory where files should be stored
        filename: Original filename
        
    Returns:
        Secure file path
    """
    # Get safe filename
    safe_name = get_safe_filename(os.path.basename(filename))
    
    # Ensure base_dir exists
    os.makedirs(base_dir, exist_ok=True)
    
    # Join paths securely
    return os.path.join(base_dir, safe_name)

def validate_pdf(file_path: str) -> bool:
    """
    Validate that a file is a valid PDF.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        True if valid, False otherwise
    """
    # Check file type
    if not validate_file_type(file_path, ["application/pdf"]):
        return False
        
    try:
        # Check PDF header
        with open(file_path, 'rb') as f:
            header = f.read(5)
            if header != b'%PDF-':
                log_error(None, f"Invalid PDF header: {header}")
                return False
                
        # Additional size validation
        file_size = os.path.getsize(file_path)
        max_size = 20 * 1024 * 1024  # 20 MB
        
        if file_size > max_size:
            log_error(None, f"PDF too large: {file_size} bytes, max allowed: {max_size} bytes")
            return False
            
        return True
        
    except Exception as e:
        log_error(e, f"Invalid PDF file: {file_path}")
        return False
