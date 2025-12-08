"""
Helper functions for file type categorization and prompt generation.
"""

import os
from typing import Dict, Any, Optional

def is_code_file(file_extension: str) -> bool:
    """
    Check if a file is a code file based on its extension.
    
    Args:
        file_extension: The file extension (e.g., '.py', '.js')
        
    Returns:
        bool: True if it's a code file, False otherwise
    """
    code_extensions = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cs', '.go', 
        '.rb', '.php', '.swift', '.kt', '.rs', '.sh', '.bash', '.ps1', '.html', 
        '.css', '.scss', '.less', '.sql', '.r', '.m', '.h', '.cc', '.scala'
    }
    return file_extension.lower() in code_extensions

def is_text_file(file_type: str, file_extension: str) -> bool:
    """
    Check if a file is a text file based on its MIME type and extension.
    
    Args:
        file_type: The MIME type (e.g., 'text/plain')
        file_extension: The file extension (e.g., '.txt')
        
    Returns:
        bool: True if it's a text file, False otherwise
    """
    if file_type.startswith('text/'):
        return True
    
    text_extensions = {
        '.txt', '.log', '.md', '.csv', '.json', '.xml', '.yaml', '.yml', 
        '.ini', '.conf', '.cfg', '.properties'
    }
    return file_extension.lower() in text_extensions

def is_document_file(file_type: str, file_extension: str) -> bool:
    """
    Check if a file is a document file based on its MIME type and extension.
    
    Args:
        file_type: The MIME type (e.g., 'application/pdf')
        file_extension: The file extension (e.g., '.pdf')
        
    Returns:
        bool: True if it's a document file, False otherwise
    """
    document_types = {
        'application/pdf', 'application/msword', 
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    }
    
    if file_type in document_types:
        return True
    
    document_extensions = {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
        '.odt', '.ods', '.odp', '.rtf'
    }
    return file_extension.lower() in document_extensions

def create_image_analysis_prompt(rep_id: str) -> str:
    """
    Create a prompt for analyzing an image attachment.
    
    Args:
        rep_id: The report ID
        
    Returns:
        str: The analysis prompt
    """
    return (
        f"Please analyze this image from report #{rep_id}.\n\n"
        f"If any content in the image is in a language other than English, please translate the key parts to English first before proceeding with your analysis.\n\n"
        f"Provide a detailed analysis of what you see in the image, focusing on: "
        f"1. What technical elements are visible (UI, code, error messages, etc.)\n"
        f"2. Any security implications visible in the content\n"
        f"3. How this relates to the vulnerability being reported\n"
        f"4. Highlight any aspects of the image that contradict or don't align with claims made in the report\n\n"
        f"Format your response as bullet points for clarity.\n\n"
        f"IMPORTANT: Do not include any statements about what you cannot do or limitations of your analysis. "
        f"If you're uncertain about something, simply focus on what you can observe and analyze with confidence."
    )

def create_code_analysis_prompt(rep_id: str, file_extension: str) -> str:
    """
    Create a prompt for analyzing a code file attachment.
    
    Args:
        rep_id: The report ID
        file_extension: The file extension
        
    Returns:
        str: The analysis prompt
    """
    return (
        f"Please analyze this code file from report #{rep_id}.\n\n"
        f"If any content in the code is in a language other than English (including comments, strings, or variable names), please translate the key parts to English first before proceeding with your analysis.\n\n"
        f"Provide a detailed analysis of the code, focusing on: "
        f"1. What language is this code written in and what does it do?\n"
        f"2. Are there any security vulnerabilities or bugs in this code?\n"
        f"3. How might this code relate to the vulnerability being reported?\n"
        f"4. Are there any best practices that are not being followed?\n"
        f"5. Highlight any elements in the code that contradict or don't support the claims made in the report\n\n"
        f"Format your response as bullet points for clarity."
    )

def create_text_analysis_prompt(rep_id: str) -> str:
    """
    Create a prompt for analyzing a text file attachment.
    
    Args:
        rep_id: The report ID
        
    Returns:
        str: The analysis prompt
    """
    return (
        f"Please analyze this text file from report #{rep_id}.\n\n"
        f"If any content in the text file is in a language other than English, please translate the key parts to English first before proceeding with your analysis.\n\n"
        f"Provide a detailed analysis of the content, focusing on: "
        f"1. What type of information is contained in this file?\n"
        f"2. Are there any security-sensitive data or configurations?\n"
        f"3. How might this information relate to the vulnerability being reported?\n"
        f"4. Are there any unusual patterns or anomalies in the text?\n"
        f"5. Highlight any information in the text that contradicts or doesn't align with claims made in the report\n\n"
        f"Format your response as bullet points for clarity."
    )

def create_document_analysis_prompt(rep_id: str) -> str:
    """
    Create a prompt for analyzing a document file attachment.
    
    Args:
        rep_id: The report ID
        
    Returns:
        str: The analysis prompt
    """
    return (
        f"Please analyze this document from report #{rep_id}.\n\n"
        f"If any content in the document is in a language other than English, please translate the key parts to English first before proceeding with your analysis.\n\n"
        f"Provide a detailed analysis of the document, focusing on: "
        f"1. What type of document is this and what information does it contain?\n"
        f"2. Are there any security-sensitive data or information?\n"
        f"3. How might this document relate to the vulnerability being reported?\n"
        f"4. Are there any unusual elements or metadata in the document?\n"
        f"5. Highlight any content in the document that contradicts or doesn't align with claims made in the report\n\n"
        f"Format your response as bullet points for clarity."
    )

def create_generic_analysis_prompt(rep_id: str, file_type: str) -> str:
    """
    Create a prompt for analyzing a generic file attachment.
    
    Args:
        rep_id: The report ID
        file_type: The file MIME type
        
    Returns:
        str: The analysis prompt
    """
    return (
        f"Please analyze this {file_type} file from report #{rep_id}.\n\n"
        f"If any content in the file is in a language other than English, please translate the key parts to English first before proceeding with your analysis.\n\n"
        f"Provide a detailed analysis of the file, focusing on: "
        f"1. What type of file is this and what might it contain?\n"
        f"2. How might this file relate to the vulnerability being reported?\n"
        f"3. Are there any security implications from this file type?\n"
        f"4. Highlight any aspects of the file that might contradict or don't align with claims made in the report\n\n"
        f"Format your response as bullet points for clarity."
    )
