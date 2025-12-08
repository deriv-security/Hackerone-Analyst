"""
Eraser API client module.
Handles interactions with the Eraser.io API for diagram generation.
"""

import requests
from typing import Dict, Any
from ..utils.logging import log_api_request, log_debug
from ..utils.secure_logging import safe_log_error
from ..config import get_eraser_api_key, get_eraser_api_base_url

class EraserAPI:
    def __init__(self):
        """Initialize the Eraser API client."""
        self.api_token = get_eraser_api_key()
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def generate_diagram_from_prompt(self, prompt: str) -> dict:
        """
        Generate a diagram using Eraser's AI diagram generation endpoint.
        
        Args:
            prompt (str): The text description of the diagram to generate
            
        Returns:
            dict: The response from Eraser's API containing the diagram data
        """
        endpoint = get_eraser_api_base_url()
        log_api_request(endpoint, f"Generating Eraser diagram from prompt")
        
        # Prepare the request payload according to API spec
        payload = {
            "text": prompt,  # Required field
            "type": "architecture",  # Specify diagram type
            "options": {
                "theme": "light",
                "format": "png",
                "layout": "vertical",
                "width": 1600,
                "height": 1200,
                "padding": 20,
                "scale": 1.5,
                "spacing": {
                    "horizontal": 80,
                    "vertical": 80
                }
            }
        }
        
        try:
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=180  # Increased timeout for diagram generation
            )
            
            # Log status code for debugging
            log_debug(f"Eraser API Status Code: {response.status_code}")
            
            # Add retries for timeouts
            retries = 3
            while retries > 0 and response.status_code >= 500:
                log_debug(f"Retrying Eraser API request... {retries} attempts left")
                response = requests.post(
                    endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout=180
                )
                retries -= 1
            
            # Handle specific error cases
            if response.status_code == 400:
                error_msg = response.text
                safe_log_error(ValueError(f"Invalid request: {error_msg}"), "Eraser API")
                raise ValueError(f"Invalid request: {error_msg}")
            elif response.status_code == 401:
                safe_log_error(ValueError("Invalid API token"), "Eraser API")
                raise ValueError("Invalid API token. Please check your token.")
            elif response.status_code == 422:
                safe_log_error(ValueError("Invalid prompt or parameters"), "Eraser API")
                raise ValueError("Invalid prompt or parameters. Please check your input.")
            
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                json_response = response.json()
                # Extract image URL if available
                if 'imageUrl' in json_response:
                    return {'url': json_response['imageUrl']}  # Convert to expected format
                else:
                    raise ValueError("No image URL in response")
            except ValueError as e:
                safe_log_error(e, "Error parsing Eraser API response")
                raise ValueError(f"Invalid JSON response: {response.text}")
            
        except requests.exceptions.RequestException as e:
            safe_log_error(e, "Error calling Eraser.io API")
            raise ValueError(f"Error calling Eraser.io API: {str(e)}")



    def generate_sequence_diagram_from_prompt(self, prompt: str) -> dict:
        """
        Generate a sequence diagram using Eraser's AI diagram generation endpoint.
        
        Args:
            prompt (str): The text description of the sequence diagram to generate
            
        Returns:
            dict: The response from Eraser's API containing the diagram data
        """
        endpoint = get_eraser_api_base_url()
        log_api_request(endpoint, f"Generating Eraser sequence diagram from prompt")
        
        # Prepare the request payload according to API spec
        payload = {
            "text": prompt,  # Required field
            "type": "sequence",  # Specify sequence diagram type
            "options": {
                "theme": "light",
                "format": "png",
                "width": 1600,
                "height": 1200,
                "padding": 20,
                "scale": 1.5
            }
        }
        
        try:
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=180  # Increased timeout for diagram generation
            )
            
            # Log status code for debugging
            log_debug(f"Eraser API Status Code: {response.status_code}")
            
            # Add retries for timeouts
            retries = 3
            while retries > 0 and response.status_code >= 500:
                log_debug(f"Retrying Eraser API request... {retries} attempts left")
                response = requests.post(
                    endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout=180
                )
                retries -= 1
            
            # Handle specific error cases
            if response.status_code == 400:
                error_msg = response.text
                safe_log_error(ValueError(f"Invalid request: {error_msg}"), "Eraser API")
                raise ValueError(f"Invalid request: {error_msg}")
            elif response.status_code == 401:
                safe_log_error(ValueError("Invalid API token"), "Eraser API")
                raise ValueError("Invalid API token. Please check your token.")
            elif response.status_code == 422:
                safe_log_error(ValueError("Invalid prompt or parameters"), "Eraser API")
                raise ValueError("Invalid prompt or parameters. Please check your input.")
            
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                json_response = response.json()
                # Extract image URL if available
                if 'imageUrl' in json_response:
                    return {'url': json_response['imageUrl']}  # Convert to expected format
                else:
                    raise ValueError("No image URL in response")
            except ValueError as e:
                safe_log_error(e, "Error parsing Eraser API response")
                raise ValueError(f"Invalid JSON response: {response.text}")
            
        except requests.exceptions.RequestException as e:
            safe_log_error(e, "Error calling Eraser.io API")
            raise ValueError(f"Error calling Eraser.io API: {str(e)}")
