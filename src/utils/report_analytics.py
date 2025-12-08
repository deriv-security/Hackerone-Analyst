"""
Report analytics utilities for generating HackerOne weekly summaries.
Extracts and analyzes report data from the HackerOne API.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from ..api.hackerone import HackerOneAPI
from ..utils.logging import log_info, log_error, log_debug
from ..utils.secret_protection import sanitize_for_logging
from ..config import get_organization_programs


class WeeklyReportAnalyzer:
    """
    Analyzer for generating weekly HackerOne report summaries.
    Extracts data from the last 7 days and provides comprehensive analytics.
    """
    
    def __init__(self):
        """Initialize the analyzer with HackerOne API client."""
        self.api = HackerOneAPI()
        self.start_time = None
        self._org_programs = None  # Cache for organization programs
        
    def fetch_individual_report(self, report_id: str) -> Dict[str, Any]:
        """
        Fetch a specific report by ID to examine its structure.
        
        Args:
            report_id: The report ID to fetch
            
        Returns:
            Report data dictionary
        """
        try:
            log_info(f"Fetching individual report {report_id}")
            response = self.api._make_request(f'reports/{report_id}', method='get', timeout=30)
            
            if 'data' in response:
                report = response['data']
                attrs = report.get('attributes', {})
                log_info(f"Report {report_id} attributes: {list(attrs.keys())}")
                log_info(f"Report {report_id} state: {attrs.get('state')}")
                log_info(f"Report {report_id} title: {attrs.get('title', 'N/A')[:100]}")
                
                # Look for any severity-related fields
                severity_fields = {k: v for k, v in attrs.items() if any(word in k.lower() for word in ['sever', 'rating', 'impact', 'cvss', 'score'])}
                log_info(f"Report {report_id} severity-related fields: {severity_fields}")
                
                return report
            else:
                log_error(None, f"No data found for report {report_id}")
                return {}
                
        except Exception as e:
            log_error(e, f"Error fetching report {report_id}")
            return {}

    def generate_weekly_summary(self) -> Dict[str, Any]:
        """
        Generate a comprehensive weekly summary of HackerOne reports.
        
        Returns:
            Dictionary containing all analytics data for the past week
        """
        self.start_time = time.time()
        log_info("Starting weekly report generation")
        
        # Note: Individual report fetching removed for production use
        # Use fetch_individual_report(report_id) method if needed for debugging
        
        try:
            # Calculate date range from current time looking back 7 days
            today = datetime.now(timezone.utc)

            # Set end date to current time
            end_date = today

            # Start date is 7 days before today
            start_date = end_date - timedelta(days=7)
            
            log_info(f"Analyzing reports from {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}")
            
            # Fetch reports for the last 7 days
            current_week_reports = self._fetch_reports_for_period(start_date, end_date)
            
            # Fetch reports for the previous 7 days (for trend analysis)
            prev_start = start_date - timedelta(days=7)
            prev_end = start_date
            previous_week_reports = self._fetch_reports_for_period(prev_start, prev_end)
            
            # Analyze the data
            summary = {
                'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'period': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                },
                'submissions': self._analyze_submissions(current_week_reports),
                'bounties': self._analyze_bounties(current_week_reports),
                'severity_breakdown': self._analyze_severity_breakdown(current_week_reports),
                'trends': self._analyze_trends(current_week_reports, previous_week_reports),
                'detailed_reports': self.get_detailed_report_list(current_week_reports),
                'processing_time': round(time.time() - self.start_time, 2)
            }
            
            log_info(f"Weekly report generated successfully in {summary['processing_time']}s")
            return summary
            
        except Exception as e:
            log_error(e, "Failed to generate weekly report summary")
            raise
    
    def _get_org_programs(self) -> List[str]:
        """
        Get configured organization programs.
        
        Returns:
            List of organization program handles
        """
        if self._org_programs is not None:
            return self._org_programs
        
        # Get programs from configuration
        self._org_programs = get_organization_programs()
        
        log_info(f"Using configured organization programs: {self._org_programs}")
        return self._org_programs
    
    def _fetch_reports_for_period(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Fetch all reports for a specific time period from all organization programs.
        
        Args:
            start_date: Start of the period (inclusive)
            end_date: End of the period (exclusive)
            
        Returns:
            List of report dictionaries from all programs
        """
        log_debug(f"Fetching reports from {start_date} to {end_date}")
        
        # Convert to ISO format for API
        start_iso = start_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_iso = end_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        # Get organization programs dynamically
        programs = self._get_org_programs()
        all_reports = []
        
        # Fetch reports from all programs
        for program in programs:
            log_info(f"Fetching reports from program: {program}")
            page = 1
            program_reports = 0
            
            while True:
                try:
                    # Use the existing HackerOne API method with date filters
                    # IMPORTANT: Program filter is REQUIRED by HackerOne API
                    filters = {
                        'filter[program][]': program,  # Required: program filter
                        'filter[created_at__gt]': start_iso,
                        'filter[created_at__lt]': end_iso,
                        'page[number]': page,
                        'page[size]': 100  # Maximum page size
                    }
                    
                    # Make the API request using the existing method pattern
                    # Include bounties and severity in the request to get actual data
                    filters['include'] = 'bounties,severity'
                    response = self.api._make_request('reports', method='get', params=filters, timeout=30)
                    
                    # Store the response for bounty analysis
                    self._current_api_response = response
                    
                    if 'data' not in response:
                        break
                        
                    reports = response['data']
                    if not reports:
                        break
                    
                    # Filter reports by date (additional client-side filtering for safety)
                    filtered_reports = []
                    for report in reports:
                        created_at = report.get('attributes', {}).get('created_at')
                        if created_at and self._is_in_date_range(created_at, start_date, end_date):
                            filtered_reports.append(report)
                    
                    all_reports.extend(filtered_reports)
                    program_reports += len(filtered_reports)
                    log_debug(f"Fetched {len(filtered_reports)} reports from {program} (page {page})")
                    
                    # Check for pagination
                    links = response.get('links', {})
                    if not links.get('next'):
                        break
                        
                    page += 1
                    
                except Exception as e:
                    log_error(e, f"Error fetching reports from {program} page {page}")
                    # Continue with other programs even if one fails
                    break
            
            log_info(f"Completed fetching from program: {program} ({program_reports} reports)")
            
            # Now fetch reports where bounty was awarded in the last 7 days
            # This is a separate query to get reports that might have been created earlier
            # but had bounties awarded during our reporting period
            log_info(f"Fetching reports with bounties awarded in the last 7 days from program: {program}")
            page = 1
            bounty_reports = 0
            
            while True:
                try:
                    # Use bounty_awarded_at filter instead of created_at
                    filters = {
                        'filter[program][]': program,  # Required: program filter
                        'filter[bounty_awarded_at__gt]': start_iso,
                        'filter[bounty_awarded_at__lt]': end_iso,
                        'page[number]': page,
                        'page[size]': 100  # Maximum page size
                    }
                    
                    # Include bounties in the request
                    filters['include'] = 'bounties,severity'
                    response = self.api._make_request('reports', method='get', params=filters, timeout=30)
                    
                    if 'data' not in response:
                        break
                        
                    reports = response['data']
                    if not reports:
                        break
                    
                    # Filter reports to ensure bounty was awarded in our date range
                    # and avoid duplicates with reports we already have
                    filtered_reports = []
                    existing_ids = {report.get('id') for report in all_reports}
                    
                    for report in reports:
                        report_id = report.get('id')
                        bounty_awarded_at = report.get('attributes', {}).get('bounty_awarded_at')
                        
                        # Only add if not already in our list and bounty was awarded in our date range
                        if (report_id not in existing_ids and 
                            bounty_awarded_at and 
                            self._is_in_date_range(bounty_awarded_at, start_date, end_date)):
                            filtered_reports.append(report)
                            existing_ids.add(report_id)
                    
                    all_reports.extend(filtered_reports)
                    bounty_reports += len(filtered_reports)
                    log_debug(f"Fetched {len(filtered_reports)} bounty-awarded reports from {program} (page {page})")
                    
                    # Check for pagination
                    links = response.get('links', {})
                    if not links.get('next'):
                        break
                        
                    page += 1
                    
                except Exception as e:
                    log_error(e, f"Error fetching bounty-awarded reports from {program} page {page}")
                    # Continue with other programs even if one fails
                    break
            
            log_info(f"Completed fetching bounty-awarded reports from program: {program} ({bounty_reports} reports)")
        
        log_info(f"Fetched {len(all_reports)} total reports from {len(programs)} programs for period")
        return all_reports
    
    
    def _is_in_date_range(self, date_str: str, start_date: datetime, end_date: datetime) -> bool:
        """
        Check if a date string falls within the specified range.
        
        Args:
            date_str: ISO date string from API
            start_date: Start of range
            end_date: End of range
            
        Returns:
            True if date is in range
        """
        try:
            report_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return start_date <= report_date < end_date
        except (ValueError, AttributeError):
            return False
    
    def _filter_actionable_reports(self, reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter out duplicate, spam, and new reports to focus on actionable submissions.
        
        Args:
            reports: List of all report dictionaries
            
        Returns:
            List of filtered report dictionaries (excluding duplicates, spam, and new reports)
        """
        actionable_reports = []
        excluded_states = {'duplicate', 'spam', 'new', 'not-applicable', 'informative', 'needs-more-info'}  # States to exclude from analysis
        
        for report in reports:
            state = report.get('attributes', {}).get('state', 'unknown')
            if state not in excluded_states:
                actionable_reports.append(report)
        
        excluded_count = len(reports) - len(actionable_reports)
        if excluded_count > 0:
            log_info(f"Filtered out {excluded_count} duplicate/spam/new reports, analyzing {len(actionable_reports)} actionable reports")
        
        return actionable_reports

    def _analyze_submissions(self, reports: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Analyze submission statistics from reports.
        
        Args:
            reports: List of report dictionaries
            
        Returns:
            Dictionary with submission counts by state
        """
        # Calculate date range from current time looking back 7 days
        today = datetime.now(timezone.utc)
        
        # Set end date to current time
        end_date = today
        
        # Start date is 7 days before today
        start_date = end_date - timedelta(days=7)
        
        # Count all reports including duplicates and spam for submission statistics
        all_state_counts = defaultdict(int)
        actionable_state_counts = defaultdict(int)
        
        # Only count reports that were created in the current reporting period
        created_in_period_reports = []
        for report in reports:
            attrs = report.get('attributes', {})
            created_at = attrs.get('created_at')
            
            # Only include reports created in the current period
            if created_at and self._is_in_date_range(created_at, start_date, end_date):
                state = attrs.get('state', 'unknown')
                all_state_counts[state] += 1
                created_in_period_reports.append(report)
        
        # Filter out duplicates and spam for actionable analysis
        actionable_reports = self._filter_actionable_reports(created_in_period_reports)
        
        # Count reports by their actual state in HackerOne
        for report in actionable_reports:
            attrs = report.get('attributes', {})
            state = attrs.get('state', 'unknown')
            actionable_state_counts[state] += 1
        
        return {
            'total': len(actionable_reports),
            'total_including_duplicates': len(reports),
            'new': actionable_state_counts.get('new', 0),
            'triaged': actionable_state_counts.get('triaged', 0),
            'needs_more_info': actionable_state_counts.get('needs-more-info', 0),
            'resolved': actionable_state_counts.get('resolved', 0),
            'informative': actionable_state_counts.get('informative', 0),
            'duplicate': all_state_counts.get('duplicate', 0),  # Show duplicates in stats
            'spam': all_state_counts.get('spam', 0),  # Show spam in stats
            'not_applicable': actionable_state_counts.get('not-applicable', 0),
            'closed': actionable_state_counts.get('resolved', 0) + actionable_state_counts.get('informative', 0) + 
                     actionable_state_counts.get('not-applicable', 0)
        }
    
    def _analyze_bounties(self, reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze bounty statistics from reports.
        
        Args:
            reports: List of report dictionaries
            
        Returns:
            Dictionary with bounty statistics and recently paid bounties
        """
        # We want to analyze all reports, not just actionable ones
        # This ensures we capture all bounty payments, even for reports in states like 'duplicate'
        
        bounty_amounts = []
        bounty_count = 0
        recently_paid_bounties = []
        reports_with_bounties_this_week = []
        
        # Calculate date range from current time looking back 7 days
        today = datetime.now(timezone.utc)
        
        # Set end date to current time
        end_date = today
        
        # Start date is 7 days before today
        start_date = end_date - timedelta(days=7)
        
        # Track which reports were created this week and also received bounties this week
        created_and_paid_this_week = set()
        
        for report in reports:
            attrs = report.get('attributes', {})
            relationships = report.get('relationships', {})
            bounties = relationships.get('bounties', {}).get('data', [])
            
            if bounties:
                bounty_count += 1
                report_bounty_total = 0
                
                # Extract bounty amounts directly from the bounty data
                for bounty in bounties:
                    # The bounty data includes attributes with amount information
                    bounty_attrs = bounty.get('attributes', {})
                    amount = bounty_attrs.get('amount')
                    bonus_amount = bounty_attrs.get('bonus_amount', '0.00')
                    
                    if amount:
                        report_bounty_total += float(amount)
                        log_debug(f"Found bounty amount: ${amount}")
                    
                    if bonus_amount and float(bonus_amount) > 0:
                        report_bounty_total += float(bonus_amount)
                        log_debug(f"Found bonus amount: ${bonus_amount}")
                
                # If we couldn't get real bounty data, fall back to estimation
                if report_bounty_total == 0:
                    # Try to get severity from relationships
                    severity_data = relationships.get('severity', {}).get('data', {})
                    severity_rating = severity_data.get('attributes', {}).get('rating', 'none')
                    report_bounty_total = self._estimate_bounty_amount(severity_rating)
                    log_debug(f"Using estimated bounty for severity {severity_rating}: ${report_bounty_total}")
                
                bounty_amounts.append(report_bounty_total)
                
                # Check if this bounty was paid in the last 7 days
                bounty_awarded_at = attrs.get('bounty_awarded_at')
                if bounty_awarded_at and self._is_in_date_range(bounty_awarded_at, start_date, end_date):
                    # Get severity from relationships
                    severity_rating = 'none'
                    severity_data_obj = relationships.get('severity', {}).get('data', {})
                    if severity_data_obj:
                        severity_rating = severity_data_obj.get('attributes', {}).get('rating', 'none')
                    
                    # Extract program information from relationships
                    program_handle = 'unknown'
                    if 'program' in relationships:
                        program_data = relationships['program'].get('data', {})
                        program_handle = program_data.get('attributes', {}).get('handle', 'unknown')
                    
                    # Format the date for display
                    try:
                        awarded_date = datetime.fromisoformat(bounty_awarded_at.replace('Z', '+00:00'))
                        formatted_date = awarded_date.strftime('%Y-%m-%d')
                    except (ValueError, AttributeError):
                        formatted_date = bounty_awarded_at
                    
                    # Add to recently paid bounties list
                    recently_paid_bounties.append({
                        'id': report.get('id'),
                        'title': sanitize_for_logging(attrs.get('title', 'N/A')),
                        'state': attrs.get('state', 'unknown'),
                        'severity': severity_rating,
                        'bounty_amount': report_bounty_total,
                        'bounty_awarded_at': bounty_awarded_at,
                        'formatted_date': formatted_date,
                        'program': program_handle
                    })
                    
                    log_info(f"Found recently paid bounty for report {report.get('id')}: ${report_bounty_total} on {formatted_date}")
        
        if bounty_amounts:
            total_amount = sum(bounty_amounts)
            average_amount = total_amount / len(bounty_amounts)
            highest_amount = max(bounty_amounts)
        else:
            total_amount = average_amount = highest_amount = 0
        
        log_info(f"Bounty analysis: {bounty_count} reports with bounties, total: ${total_amount}")
        log_info(f"Found {len(recently_paid_bounties)} bounties paid in the last 7 days")
        
        # Sort recently paid bounties by date (newest first)
        recently_paid_bounties.sort(key=lambda x: x.get('bounty_awarded_at', ''), reverse=True)
        
        return {
            'count': bounty_count,
            'total_amount': total_amount,
            'average_amount': average_amount,
            'highest_amount': highest_amount,
            'recently_paid': recently_paid_bounties
        }
    
    def _estimate_bounty_amount(self, severity: str) -> float:
        """
        Estimate bounty amount based on severity rating.
        This is a placeholder - in production you'd fetch actual amounts.
        
        Args:
            severity: Severity rating string
            
        Returns:
            Estimated bounty amount
        """
        severity_amounts = {
            'critical': 2500.0,
            'high': 1000.0,
            'medium': 500.0,
            'low': 100.0,
            'none': 0.0
        }
        return severity_amounts.get(severity.lower(), 0.0)
    
    def _analyze_severity_breakdown(self, reports: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze reports by severity level.
        
        Args:
            reports: List of report dictionaries
            
        Returns:
            Dictionary with severity breakdown
        """
        # Calculate date range from current time looking back 7 days
        today = datetime.now(timezone.utc)
        
        # Set end date to current time
        end_date = today
        
        # Start date is 7 days before today
        start_date = end_date - timedelta(days=7)
        
        # Only consider reports that were created in the current reporting period
        created_in_period_reports = []
        for report in reports:
            attrs = report.get('attributes', {})
            created_at = attrs.get('created_at')
            
            # Only include reports created in the current period
            if created_at and self._is_in_date_range(created_at, start_date, end_date):
                created_in_period_reports.append(report)
        
        # Filter out duplicates and spam for meaningful analysis
        actionable_reports = self._filter_actionable_reports(created_in_period_reports)
        
        severity_data = defaultdict(lambda: {'count': 0, 'bounty_total': 0.0})
        
        for i, report in enumerate(actionable_reports):
            attrs = report.get('attributes', {})
            relationships = report.get('relationships', {})
            
            # Get severity rating from relationships (not attributes)
            # Based on our test, severity data is in relationships['severity']['data']
            severity_rating = None
            severity_data_obj = relationships.get('severity', {}).get('data', {})
            if severity_data_obj:
                severity_rating = severity_data_obj.get('attributes', {}).get('rating')
            
            # Log first 10 reports to understand the data structure
            if i < 10:
                log_info(f"Report {report.get('id')}: severity_rating={severity_rating}, "
                        f"state={attrs.get('state')}, title={attrs.get('title', 'N/A')[:50]}")
                if severity_rating == 'critical':
                    log_info(f"CRITICAL REPORT FOUND: {severity_data_obj}")
            
            # Handle different severity values
            if severity_rating is None or severity_rating == '':
                # For reports without severity (usually new/untriaged), use state to infer
                state = attrs.get('state', 'unknown')
                if state in ['new', 'needs-more-info']:
                    severity = 'pending'  # Special category for unassessed reports
                else:
                    severity = 'none'
            else:
                severity = str(severity_rating).lower()
            
            severity_data[severity]['count'] += 1
            
            # Add actual bounty amount if report has bounties
            bounties = relationships.get('bounties', {}).get('data', [])
            if bounties:
                # Calculate actual bounty total for this report
                report_bounty_total = 0
                for bounty in bounties:
                    bounty_attrs = bounty.get('attributes', {})
                    amount = bounty_attrs.get('amount')
                    bonus_amount = bounty_attrs.get('bonus_amount', '0.00')
                    
                    if amount:
                        report_bounty_total += float(amount)
                    if bonus_amount and float(bonus_amount) > 0:
                        report_bounty_total += float(bonus_amount)
                
                # Use actual amount if available, otherwise estimate
                if report_bounty_total > 0:
                    severity_data[severity]['bounty_total'] += report_bounty_total
                else:
                    estimated_amount = self._estimate_bounty_amount(severity)
                    severity_data[severity]['bounty_total'] += estimated_amount
        
        log_info(f"Severity breakdown: {dict(severity_data)}")
        return dict(severity_data)
    
    
    def _analyze_trends(self, current_reports: List[Dict[str, Any]], 
                       previous_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze trends compared to the previous week.
        
        Args:
            current_reports: Reports from current week
            previous_reports: Reports from previous week
            
        Returns:
            Dictionary with trend analysis
        """
        current_bounties = self._analyze_bounties(current_reports)
        previous_bounties = self._analyze_bounties(previous_reports)
        
        return {
            'report_change': len(current_reports) - len(previous_reports),
            'bounty_change': current_bounties['total_amount'] - previous_bounties['total_amount'],
            'bounty_count_change': current_bounties['count'] - previous_bounties['count']
        }
    
    def get_detailed_report_list(self, reports: List[Dict[str, Any]], 
                                limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get a detailed list of the most significant reports.
        
        Args:
            reports: List of report dictionaries
            limit: Maximum number of reports to return
            
        Returns:
            List of formatted report summaries
        """
        # Calculate date range from current time looking back 7 days
        today = datetime.now(timezone.utc)
        
        # Set end date to current time
        end_date = today
        
        # Start date is 7 days before today
        start_date = end_date - timedelta(days=7)
        
        # Filter out duplicates and spam for meaningful analysis
        actionable_reports = self._filter_actionable_reports(reports)
        
        # Helper function to get severity from relationships
        def get_severity_rating(report):
            relationships = report.get('relationships', {})
            severity_data_obj = relationships.get('severity', {}).get('data', {})
            if severity_data_obj:
                return severity_data_obj.get('attributes', {}).get('rating', 'none')
            return 'none'
        
        # Sort by bounty first (reports with bounties come first), then by severity, then by creation date
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'none': 4}
        
        def get_bounty_amount(report):
            """Get total bounty amount for sorting purposes."""
            relationships = report.get('relationships', {})
            bounties = relationships.get('bounties', {}).get('data', [])
            total = 0.0
            for bounty in bounties:
                bounty_attrs = bounty.get('attributes', {})
                amount = bounty_attrs.get('amount')
                bonus_amount = bounty_attrs.get('bonus_amount', '0.00')
                if amount:
                    total += float(amount)
                if bonus_amount and float(bonus_amount) > 0:
                    total += float(bonus_amount)
            return total
        
        sorted_reports = sorted(
            actionable_reports,
            key=lambda r: (
                -1 if get_bounty_amount(r) > 0 else 0,  # Reports with bounties first (negative for reverse order)
                severity_order.get(get_severity_rating(r).lower(), 5),
                r.get('attributes', {}).get('created_at', '')
            )
        )
        
        detailed_reports = []
        for report in sorted_reports[:limit]:
            attrs = report.get('attributes', {})
            relationships = report.get('relationships', {})
            
            # Extract program information from relationships
            program_handle = 'unknown'
            if 'program' in relationships:
                program_data = relationships['program'].get('data', {})
                program_handle = program_data.get('attributes', {}).get('handle', 'unknown')
            
            # Get severity from relationships
            severity_rating = get_severity_rating(report)
            
            # Calculate bounty amount for this specific report
            bounty_amount = 0.0
            bounties = relationships.get('bounties', {}).get('data', [])
            for bounty in bounties:
                bounty_attrs = bounty.get('attributes', {})
                amount = bounty_attrs.get('amount')
                bonus_amount = bounty_attrs.get('bonus_amount', '0.00')
                
                if amount:
                    bounty_amount += float(amount)
                if bonus_amount and float(bonus_amount) > 0:
                    bounty_amount += float(bonus_amount)
            
            # Check if this report had a bounty awarded in the current week
            bounty_awarded_at = attrs.get('bounty_awarded_at')
            bounty_awarded_this_week = (
                bounty_awarded_at and 
                self._is_in_date_range(bounty_awarded_at, start_date, end_date)
            )
            
            # Check if this report was created in the current week
            created_at = attrs.get('created_at')
            created_this_week = (
                created_at and 
                self._is_in_date_range(created_at, start_date, end_date)
            )
            
            detailed_reports.append({
                'id': report.get('id'),
                'title': sanitize_for_logging(attrs.get('title', 'N/A')),
                'state': attrs.get('state', 'unknown'),
                'severity': severity_rating,
                'created_at': attrs.get('created_at', ''),
                'program': program_handle,
                'has_bounty': bool(bounties),
                'bounty_amount': bounty_amount,
                'bounty_awarded_at': bounty_awarded_at,
                'bounty_awarded_this_week': bounty_awarded_this_week,
                'created_this_week': created_this_week
            })
        
        return detailed_reports
