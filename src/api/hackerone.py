"""
HackerOne API client module.
Handles all interactions with the HackerOne API.
"""

import json
import logging
import requests
import base64
from io import BytesIO
from PIL import Image
from typing import Dict, Any, List, Optional, Tuple
from ..utils.logging import log_api_request, log_debug, log_info
from ..utils.secure_logging import safe_log_error, safe_log_response_error, safe_log_debug_response
from ..config import get_hackerone_auth, get_api_timeout
from ..utils.url_processing import process_report_content

class HackerOneAPI:
    """Client for interacting with the HackerOne API."""
    
    def __init__(self):
        """Initialize the HackerOne API client."""
        from ..config import get_hackerone_api_base_url
        self.BASE_URL = get_hackerone_api_base_url()
        self.auth = get_hackerone_auth()
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def _make_request(
        self,
        endpoint: str,
        method: str = 'get',
        json_data: Optional[Dict] = None,
        timeout: Optional[int] = None,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Make an API request to HackerOne.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (get/post)
            json_data: Optional JSON data for POST requests
            timeout: Optional timeout override (defaults to API_TIMEOUT from config)
            
        Returns:
            Dict containing the API response
            
        Raises:
            Exception: If the API request fails
        """
        # Use the timeout from config if not explicitly provided
        if timeout is None:
            timeout = get_api_timeout()
            
        url = f"{self.BASE_URL}/{endpoint}"
        
        # Determine the purpose of the API request for logging
        if 'completions' in endpoint and method.lower() == 'post':
            if json_data and 'data' in json_data and 'attributes' in json_data['data']:
                if 'report_ids' in json_data['data']['attributes']:
                    rep_id = json_data['data']['attributes']['report_ids'][0]
                    # Check if this is a question by looking at the prompt
                    if 'messages' in json_data['data']['attributes'] and json_data['data']['attributes']['messages']:
                        message_content = json_data['data']['attributes']['messages'][0].get('content', '')
                        if 'Please answer the following question' in message_content:
                            purpose = f"Sending question for report ID {rep_id}"
                        else:
                            purpose = f"Requesting report analysis for ID {rep_id}"
                    else:
                        purpose = f"Requesting report analysis for ID {rep_id}"
                else:
                    purpose = "Creating new completion"
            else:
                purpose = "Creating new completion"
        elif 'completions' in endpoint and method.lower() == 'get':
            comp_id = endpoint.split('/')[-1]
            purpose = f"Checking completion status for ID {comp_id}"
        elif 'users' in endpoint:
            username = endpoint.split('/')[-1]
            purpose = f"Fetching user profile for {username}"
        elif 'reports' in endpoint and 'state_changes' in endpoint:
            rep_id = endpoint.split('/')[-2]
            purpose = f"Changing state for report {rep_id}"
        elif 'reports' in endpoint:
            rep_id = endpoint.split('/')[-1].split('?')[0]  # Remove query params
            purpose = f"Fetching details for report {rep_id}"
        else:
            purpose = f"Making request to {endpoint}"
        
        # Log the request
        log_api_request(url, purpose)
        
        try:
            if method.lower() == 'post':
                response = requests.post(
                    url,
                    auth=self.auth,
                    json=json_data,
                    headers=self.headers,
                    timeout=timeout
                )
            else:
                response = requests.get(
                    url,
                    auth=self.auth,
                    headers=self.headers,
                    params=params,
                    timeout=timeout
                )
            
            # Log response status at debug level only
            log_debug(f"Response received from {url}: {response.status_code}")
            
            # Log full response details at debug level only (sanitized)
            safe_log_debug_response(response.text)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Use secure logging to avoid exposing secrets
            safe_log_response_error(e, url, getattr(e, 'response', None))
            raise Exception(f"API request failed: {str(e)}")
        
        except json.JSONDecodeError as e:
            safe_log_error(e, "Failed to parse API response")
            # Never log raw response content - it may contain secrets
            if 'response' in locals():
                logging.error("Raw response: [REDACTED FOR SECURITY]")
            raise Exception("Failed to parse API response")
    
    def get_report(self, report_id: str, include_attachments: bool = True) -> Dict[str, Any]:
        """
        Get full report details from HackerOne.
        
        Args:
            report_id: The HackerOne report ID
            include_attachments: Whether to include attachments in the response
            
        Returns:
            Dict containing the report details
        """
        endpoint = f"reports/{report_id}"
        # No query parameters needed, attachments are included by default
        return self._make_request(endpoint)
    
    def _download_and_encode_image(self, image_url: str, max_size: int = 800) -> str:
        """
        Download an image from URL and encode it to base64.
        
        Args:
            image_url: URL of the image to download
            max_size: Maximum width or height to resize to (to reduce size)
            
        Returns:
            Base64 encoded string of the image
        """
        try:
            # Download the image
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            
            # Open and potentially resize the image
            img = Image.open(BytesIO(response.content))
            
            # Resize if needed
            width, height = img.size
            if width > max_size or height > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # Convert to bytes
            buffer = BytesIO()
            # Convert RGBA to RGB if needed (for transparent PNGs)
            if img.mode == 'RGBA':
                # Create a white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                # Paste the image with transparency on the background
                background.paste(img, mask=img.split()[3])  # 3 is the alpha channel
                img = background
            
            img.save(buffer, format="JPEG")
            img_bytes = buffer.getvalue()
            
            # Encode to base64
            base64_encoded = base64.b64encode(img_bytes).decode('utf-8')
            
            return base64_encoded
            
        except Exception as e:
            safe_log_error(e, "Error downloading and encoding image")
            return ""
    
    def analyze_report(self, report_id: str, prompt: str, image_url: str = None, timeout: Optional[int] = None) -> str:
        """
        Analyze a report using HackerOne's Hai endpoint.
        
        Args:
            report_id: The HackerOne report ID
            prompt: The analysis prompt
            image_url: Optional URL to an image to include in the analysis
            timeout: Optional timeout override (defaults to API_TIMEOUT from config)
            
        Returns:
            String containing the Hai analysis
        """
        # Process the prompt to handle long URLs and content length
        processed_prompt = process_report_content(prompt, max_url_length=200, max_total_length=8000)
        
        if len(processed_prompt) != len(prompt):
            log_info(f"Processed prompt content: reduced from {len(prompt)} to {len(processed_prompt)} characters")
        
        # If an image URL is provided, download and encode it
        if image_url:
            try:
                # Download and encode the image
                base64_image = self._download_and_encode_image(image_url)
                
                # Add the image data to the prompt
                if base64_image:
                    processed_prompt = (
                        f"{processed_prompt}\n\n"
                        f"I'm including a base64-encoded image for you to analyze. "
                        f"The image is included inline below:\n"
                        f"data:image/jpeg;base64,{base64_image}"
                    )
            except Exception as e:
                safe_log_error(e, f"Error processing image for Hai")
                # Continue without the image if there's an error
        data = {
            "data": {
                "type": "completion-request",
                "attributes": {
                    "messages": [{"role": "user", "content": processed_prompt}],
                    "program_handles": ["string"],
                    "report_ids": [report_id],
                    "cve_ids": ["string"],
                    "cwe_ids": ["string"]
                }
            },
            "required": 'null'
        }
        
        # Create completion request
        response = self._make_request(
            "hai/chat/completions",
            method='post',
            json_data=data,
            timeout=timeout
        )
        
        completion_id = response['data']['id']
        
        # Poll for completion
        import time
        from ..utils.logging import log_info, log_debug
        
        # Calculate max retries based on the API timeout
        # If we want the total polling time to be roughly equal to the API timeout,
        # and we sleep for 2 seconds between retries, then:
        api_timeout = timeout if timeout is not None else get_api_timeout()
        max_retries = max(1, api_timeout // 2)  # At least 1 retry, otherwise timeout/2
        retry_count = 0
        
        # Log first check at INFO level
        log_info(f"Waiting for Hai completion {completion_id} (checking every 2s, max {max_retries} retries)")
        
        while retry_count < max_retries:
            # Use a lower-level direct request to avoid noisy INFO logs for status checks
            url = f"{self.BASE_URL}/hai/chat/completions/{completion_id}"
            try:
                response = requests.get(
                    url,
                    auth=self.auth,
                    headers=self.headers,
                    timeout=timeout if timeout is not None else get_api_timeout()
                )
                response.raise_for_status()
                status_response = response.json()
                
                # Log status check at DEBUG level only
                log_debug(f"Hai completion status check {retry_count+1}/{max_retries}: {status_response['data']['attributes']['state']}")
                
                state = status_response['data']['attributes']['state']
                
                if state == "completed":
                    log_info(f"Hai completion {completion_id} finished successfully")
                    return status_response['data']['attributes']['response']
            except Exception as e:
                safe_log_error(e, f"Error checking Hai completion status (retry {retry_count+1}/{max_retries})")
                # Continue with retries even if one status check fails
            
            time.sleep(2)
            retry_count += 1
        
        raise TimeoutError("Hai analysis timed out")
    
    def get_report_attachments(self, report_id: str, report: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Get attachments for a report.
        
        Args:
            report_id: The HackerOne report ID
            report: Optional report data to extract attachments from
            
        Returns:
            List of attachment details
        """
        try:
            if report is None:
                report = self.get_report(report_id)
            
            formatted_attachments = []
            log_api_request(f"{self.BASE_URL}/reports/{report_id}", "Extracting attachments from report")
            
            # Check for attachments directly in the relationships
            if 'data' in report and 'relationships' in report['data'] and 'attachments' in report['data']['relationships']:
                attachments_data = report['data']['relationships']['attachments']
                # Extract just the IDs and filenames for logging
                attachment_info = []
                if 'data' in attachments_data:
                    for att in attachments_data['data']:
                        if 'id' in att and 'attributes' in att and 'file_name' in att['attributes']:
                            attachment_info.append(f"{att['id']}:{att['attributes']['file_name']}")
                
                log_api_request(f"{self.BASE_URL}/reports/{report_id}", 
                              f"Found attachments in relationships: {', '.join(attachment_info)}")
                
                if 'data' not in attachments_data or not attachments_data['data']:
                    log_api_request(f"{self.BASE_URL}/reports/{report_id}", "No attachment data found")
                    return []
                
                attachment_items = attachments_data['data']
                log_api_request(f"{self.BASE_URL}/reports/{report_id}", f"Found {len(attachment_items)} attachments")
            else:
                log_api_request(f"{self.BASE_URL}/reports/{report_id}", "No attachments found in relationships")
                return []
            
            # Process each attachment from the relationships data
            for item in attachment_items:
                attachment_id = item.get('id', '')
                if not attachment_id:
                    continue
                    
                # The attributes are available directly in the relationship data
                if 'attributes' in item:
                    attrs = item.get('attributes', {})
                    
                    # Create attachment object with proper ID format for matching in text
                    if 'expiring_url' in attrs and 'file_name' in attrs:
                        attachment = {
                            'id': attachment_id,  # The raw ID from the API
                            'url': attrs.get('expiring_url', ''),
                            'filename': attrs.get('file_name', ''),
                            'type': attrs.get('content_type', ''),
                            'size': attrs.get('file_size', 0)
                        }
                        
                        # Add the attachment to our list
                        formatted_attachments.append(attachment)
                        log_api_request(f"{self.BASE_URL}/reports/{report_id}", 
                                      f"Added attachment: ID={attachment_id}, filename={attrs.get('file_name', '')}")
            
            return formatted_attachments
            
        except Exception as e:
            safe_log_error(e, "Could not fetch attachments from report")
            return []
    
    def get_user_profile(self, username: str) -> Dict[str, Any]:
        """
        Get a user's profile from HackerOne.
        
        Args:
            username: The HackerOne username
            
        Returns:
            Dict containing the user's profile information
        """
        try:
            response = self._make_request(f"users/{username}")
            
            # Extract user data from response
            user_data = response.get('data', {}).get('attributes', {})
            
            # Format impact and signal to 2 decimal places if they are numbers
            impact = user_data.get('impact', 'N/A')
            signal = user_data.get('signal', 'N/A')
            
            if isinstance(impact, (int, float)):
                impact = f"{impact:.2f}"
            
            if isinstance(signal, (int, float)):
                signal = f"{signal:.2f}"
            
            from ..config import get_hackerone_web_base_url
            profile = {
                'username': username,
                'url': f"{get_hackerone_web_base_url()}/{username}?type=user",
                'reputation': str(user_data.get('reputation', 'N/A')),
                'impact': impact,
                'signal': signal,
                'rank': 'N/A'  # API doesn't provide rank directly
            }
            
            # Add profile picture if available
            profile_pictures = user_data.get('profile_picture', {})
            if profile_pictures:
                # Always use the 62x62 version if available
                if '62x62' in profile_pictures:
                    profile_pic_url = profile_pictures['62x62']
                elif '82x82' in profile_pictures:
                    profile_pic_url = profile_pictures['82x82']
                elif '110x110' in profile_pictures:
                    profile_pic_url = profile_pictures['110x110']
                elif '260x260' in profile_pictures:
                    profile_pic_url = profile_pictures['260x260']
                else:
                    profile['profile_picture'] = self.get_default_profile_picture()
                    profile_pic_url = None
                
                if profile_pic_url:
                    # Handle relative URLs
                    if profile_pic_url.startswith('/'):
                        profile_pic_url = f"{get_hackerone_web_base_url()}{profile_pic_url}"
                    elif not profile_pic_url.startswith(('http://', 'https://')):
                        profile_pic_url = self.get_default_profile_picture()
                    
                    profile['profile_picture'] = profile_pic_url
            else:
                profile['profile_picture'] = self.get_default_profile_picture()
            
            # Add created_at date if available
            if 'created_at' in user_data:
                created_at = user_data.get('created_at', '')
                if created_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        profile['joined'] = dt.strftime('%b %d, %Y')
                    except:
                        profile['joined'] = created_at
            
            return profile
            
        except Exception as e:
            safe_log_error(e, f"Failed to fetch profile for {username}")
            from ..config import get_hackerone_web_base_url
            return {
                'username': username,
                'url': f"{get_hackerone_web_base_url()}/{username}?type=user",
                'reputation': 'N/A',
                'impact': 'N/A',
                'signal': 'N/A',
                'reports': 'N/A',
                'rank': 'N/A',
                'joined': 'N/A'
            }
    
    def acknowledge_report(self, report_id: str, message: Optional[str] = None) -> Dict[str, Any]:
        """
        Acknowledge a report by changing its state to triaged.
        
        Args:
            report_id: The HackerOne report ID
            message: Optional message to include with the state change
            
        Returns:
            Dict containing the API response
        """
        if message is None:
            message = (
                "Thank you for submitting this report to our bug bounty program! "
                "We appreciate you taking the time to help improve our security. "
                "Our team will investigate this issue thoroughly and get back to you with our findings. "
                "We've changed the status to 'triaged' while we look into this further."
            )
        
        data = {
            "data": {
                "type": "state-change",
                "attributes": {
                    "message": message,
                    "state": "triaged"
                }
            }
        }
        
        return self._make_request(
            f"reports/{report_id}/state_changes",
            method='post',
            json_data=data
        )
    
    def get_analytics(self, key: str, program_handle: str = None, interval: str = "month", 
                     start_at: str = "2012-01-01", end_at: str = None) -> Dict[str, Any]:
        """
        Get analytics data from HackerOne.

        Args:
            key: The analytics key for the desired metric
            program_handle: Optional program handle to filter by
            interval: Time interval for the data
            start_at: Start date for the analytics
            end_at: End date for the analytics
            
        Returns:
            Dict containing the analytics response
        """
        from datetime import datetime
        
        # Set end_at to today if not provided
        if end_at is None:
            end_at = datetime.now().strftime('%Y-%m-%d')
        
        params = {
            'key': key,
            'interval': interval,
            'start_at': start_at,
            'end_at': end_at
        }
        
        # Add program handle if specified
        if program_handle:
            params['program_handle'] = program_handle
        
        return self._make_request("analytics", params=params)
    
    @staticmethod
    def get_default_profile_picture() -> str:
        """Get the URL for the default profile picture."""
        from ..config import get_hackerone_default_avatar_url
        return get_hackerone_default_avatar_url()
        
    def get_organization_members(self, organization_name: str = None) -> List[Dict[str, Any]]:
        """
        Get all members of an organization from HackerOne.
        
        Args:
            organization_name: Optional organization name or ID. If not provided, 
                               will first get the organization ID using the /me/organizations endpoint.
                               
        Returns:
            List of dictionaries containing member information
        """
        try:
            log_info(f"Fetching organization members")
            
            # First, we need to get the organization ID if not provided
            organization_id = organization_name
            
            if not organization_id:
                # Get the list of organizations the API token has access to
                log_info("No organization ID provided, fetching from /me/organizations")
                try:
                    orgs_response = self._make_request("me/organizations")
                    
                    if 'data' not in orgs_response or not orgs_response['data']:
                        raise ValueError("No organizations found for this API token")
                    
                    # Use the ID of the first organization
                    organization_id = orgs_response['data'][0]['id']
                    log_info(f"Using organization ID: {organization_id}")
                except Exception as e:
                    safe_log_error(e, "Failed to fetch organization ID")
                    raise ValueError(f"Failed to fetch organization ID: {str(e)}")
            
            # Now get the members using the correct endpoint with pagination
            log_info(f"Fetching members for organization ID: {organization_id}")
            
            all_members = []
            page = 1
            total_fetched = 0
            
            # Fetch all pages of results
            while True:
                # Use the correct endpoint from the API documentation with pagination
                params = {
                    'page[number]': page,
                    'page[size]': 100  # Maximum page size to reduce number of requests
                }
                
                members_response = self._make_request(
                    f"organizations/{organization_id}/members",
                    params=params
                )
                
                if 'data' not in members_response or not members_response['data']:
                    # No more data to fetch
                    break
                
                members = members_response['data']
                page_count = len(members)
                total_fetched += page_count
                log_info(f"Fetched page {page} with {page_count} members (total: {total_fetched})")
                
                all_members.extend(members)
                
                # Check if there are more pages
                if 'links' in members_response and 'next' in members_response['links'] and members_response['links']['next']:
                    page += 1
                else:
                    # No more pages
                    break
            
            if not all_members:
                log_info("No members found in the organization")
                return []
            
            log_info(f"Successfully fetched {len(all_members)} members across {page} pages")
            
            # Process each member to extract all available fields
            processed_members = []
            for member in all_members:
                member_data = {
                    'id': member.get('id', ''),
                    'type': member.get('type', '')
                }
                
                # Extract all attributes
                if 'attributes' in member:
                    attrs = member['attributes']
                    for key, value in attrs.items():
                        member_data[key] = value
                
                # Extract relationships if available
                if 'relationships' in member:
                    for rel_name, rel_data in member['relationships'].items():
                        if 'data' in rel_data:
                            if isinstance(rel_data['data'], dict):
                                rel_id = rel_data['data'].get('id')
                                member_data[f"{rel_name}_id"] = rel_id
                            elif isinstance(rel_data['data'], list):
                                rel_ids = [item.get('id') for item in rel_data['data'] if isinstance(item, dict) and 'id' in item]
                                member_data[f"{rel_name}_ids"] = rel_ids
                
                processed_members.append(member_data)
            
            log_info(f"Successfully processed {len(processed_members)} members")
            return processed_members
            
        except Exception as e:
            safe_log_error(e, f"Failed to fetch organization members")
            raise ValueError(f"Failed to fetch organization members: {str(e)}")
