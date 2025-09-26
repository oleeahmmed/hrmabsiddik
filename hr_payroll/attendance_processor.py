# zkteco/attendance_processor.py
import logging
from datetime import timedelta, datetime, time
from django.utils import timezone
from collections import defaultdict
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal

from .models import Employee, Shift, Attendance, AttendanceLog, Holiday, LeaveApplication, Department, Designation

logger = logging.getLogger(__name__)

class EnhancedAttendanceProcessor:
    """
    Enhanced Unified Attendance Processing System for ZKTeco Integration
    
    Features:
    - Minimum Working Hours Rule (Intime + Outtime Duration)
    - Half Day Rule Based on Working Hours
    - In-time and Out-time Both Must Rule
    - Maximum Allowable Working Hours Rule
    - Dynamic Shift Detection Override Rule
    - Grace Time per Shift Instead of Global
    - Consecutive Absence to Flag as Termination Risk
    - Max Early Out Threshold
    """
    
    def __init__(self, config_data=None):
        """Initialize with comprehensive configuration data."""
        if config_data is None:
            config_data = {}
            
        # Basic Configuration with defaults
        self.weekend_days = [int(day) for day in config_data.get('weekend_days', [4])]  # Friday default
        self.grace_minutes = int(config_data.get('grace_minutes', 15))
        self.early_out_threshold = int(config_data.get('early_out_threshold_minutes', 30))
        self.overtime_start_after = int(config_data.get('overtime_start_after_minutes', 15))
        self.minimum_overtime_minutes = int(config_data.get('minimum_overtime_minutes', 60))
        
        # New Rule 1: Minimum Working Hours Rule
        self.minimum_working_hours_for_present = float(config_data.get('minimum_working_hours_for_present', 4))
        self.enable_minimum_working_hours_rule = config_data.get('enable_minimum_working_hours_rule', False)
        
        # New Rule 2: Half Day Rule Based on Working Hours
        self.half_day_minimum_hours = float(config_data.get('half_day_minimum_hours', 4))
        self.half_day_maximum_hours = float(config_data.get('half_day_maximum_hours', 6))
        self.enable_working_hours_half_day_rule = config_data.get('enable_working_hours_half_day_rule', False)
        
        # New Rule 3: In-time and Out-time Both Must Rule
        self.require_both_in_and_out = config_data.get('require_both_in_and_out', False)
        
        # New Rule 4: Maximum Allowable Working Hours Rule
        self.maximum_allowable_working_hours = float(config_data.get('maximum_allowable_working_hours', 16))
        self.enable_maximum_working_hours_rule = config_data.get('enable_maximum_working_hours_rule', False)
        
        # New Rule 5: Dynamic Shift Detection Override Rule
        self.enable_dynamic_shift_detection = config_data.get('enable_dynamic_shift_detection', False)
        self.dynamic_shift_tolerance_minutes = int(config_data.get('dynamic_shift_tolerance_minutes', 30))
        self.multiple_shift_priority = config_data.get('multiple_shift_priority', 'least_break')
        self.dynamic_shift_fallback_to_default = config_data.get('dynamic_shift_fallback_to_default', True)
        self.dynamic_shift_fallback_shift_id = config_data.get('dynamic_shift_fallback_shift_id')
        
        # New Rule 6: Grace Time per Shift Instead of Global
        self.use_shift_grace_time = config_data.get('use_shift_grace_time', False)
        
        # New Rule 7: Consecutive Absence to Flag as Termination Risk
        self.consecutive_absence_termination_risk_days = int(config_data.get('consecutive_absence_termination_risk_days', 5))
        self.enable_consecutive_absence_flagging = config_data.get('enable_consecutive_absence_flagging', False)
        
        # New Rule 8: Max Early Out Threshold
        self.max_early_out_threshold_minutes = int(config_data.get('max_early_out_threshold_minutes', 120))
        self.max_early_out_occurrences = int(config_data.get('max_early_out_occurrences', 3))
        self.enable_max_early_out_flagging = config_data.get('enable_max_early_out_flagging', False)
        
        # Enhanced Overtime Configuration
        self.overtime_calculation_method = config_data.get('overtime_calculation_method', 'shift_based')
        self.holiday_overtime_full_day = config_data.get('holiday_overtime_full_day', True)
        self.weekend_overtime_full_day = config_data.get('weekend_overtime_full_day', True)
        self.late_affects_overtime = config_data.get('late_affects_overtime', False)
        self.separate_ot_break_time = int(config_data.get('separate_ot_break_time', 0))
        
        # Break Time Configuration
        self.use_shift_break_time = config_data.get('use_shift_break_time', True)
        self.default_break_minutes = int(config_data.get('default_break_minutes', 60))
        self.break_deduction_method = config_data.get('break_deduction_method', 'fixed')
        
        # Advanced Rules
        self.late_to_absent_days = int(config_data.get('late_to_absent_days', 3))
        self.holiday_before_after_absent = config_data.get('holiday_before_after_absent', True)
        self.weekend_before_after_absent = config_data.get('weekend_before_after_absent', True)
        self.require_holiday_presence = config_data.get('require_holiday_presence', False)
        self.include_holiday_analysis = config_data.get('include_holiday_analysis', True)
        self.holiday_buffer_days = int(config_data.get('holiday_buffer_days', 1))
        
        # Employee Override Settings
        self.use_employee_specific_grace = config_data.get('use_employee_specific_grace', True)
        self.use_employee_specific_overtime = config_data.get('use_employee_specific_overtime', True)
        self.use_employee_expected_hours = config_data.get('use_employee_expected_hours', True)
        
        # Cache for performance
        self._shift_cache = {}
        self._employee_cache = {}
        
        # Display Options
        self.show_absent_employees = config_data.get('show_absent_employees', True)
        self.show_leave_employees = config_data.get('show_leave_employees', True)
        self.show_holiday_status = config_data.get('show_holiday_status', True)
        self.include_roster_info = config_data.get('include_roster_info', True)
    
    def get_config_summary(self):
        """Get current configuration summary for display."""
        return {
            'basic_settings': {
                'grace_minutes': self.grace_minutes,
                'early_out_threshold': self.early_out_threshold,
                'overtime_start_after': self.overtime_start_after,
                'minimum_overtime_minutes': self.minimum_overtime_minutes,
            },
            'new_rules': {
                'minimum_working_hours_for_present': self.minimum_working_hours_for_present,
                'enable_minimum_working_hours_rule': self.enable_minimum_working_hours_rule,
                'half_day_minimum_hours': self.half_day_minimum_hours,
                'half_day_maximum_hours': self.half_day_maximum_hours,
                'enable_working_hours_half_day_rule': self.enable_working_hours_half_day_rule,
                'require_both_in_and_out': self.require_both_in_and_out,
                'maximum_allowable_working_hours': self.maximum_allowable_working_hours,
                'enable_maximum_working_hours_rule': self.enable_maximum_working_hours_rule,
                'use_shift_grace_time': self.use_shift_grace_time,
                'consecutive_absence_termination_risk_days': self.consecutive_absence_termination_risk_days,
                'enable_consecutive_absence_flagging': self.enable_consecutive_absence_flagging,
            },
            'shift_detection': {
                'dynamic_enabled': self.enable_dynamic_shift_detection,
                'tolerance_minutes': self.dynamic_shift_tolerance_minutes,
                'multiple_shift_priority': self.multiple_shift_priority,
                'fallback_to_default': self.dynamic_shift_fallback_to_default,
            },
            'overtime_rules': {
                'calculation_method': self.overtime_calculation_method,
                'holiday_full_day': self.holiday_overtime_full_day,
                'weekend_full_day': self.weekend_overtime_full_day,
                'late_affects_ot': self.late_affects_overtime,
                'separate_ot_break': self.separate_ot_break_time,
            },
            'break_time': {
                'use_shift_break': self.use_shift_break_time,
                'default_break_minutes': self.default_break_minutes,
                'deduction_method': self.break_deduction_method,
            },
            'weekend_days': self.weekend_days,
        }
    
    def process_employee_attendance(self, employee, attendance_date, zk_logs=None, 
                                  holidays=None, leave_applications=None, roster_data=None):
        """
        Process attendance for a single employee on a specific date.
        Returns daily attendance record with comprehensive analysis.
        """
        
        # Initialize the record
        record = {
            'employee': employee,
            'employee_id': employee.employee_id,
            'employee_name': employee.name,
            'department': employee.department.name if employee.department else 'N/A',
            'designation': employee.designation.name if employee.designation else 'N/A',
            'date': attendance_date,
            'day_name': attendance_date.strftime('%A'),
            'status': 'A',  # Default to absent
            'original_status': 'A',
            'in_time': None,
            'out_time': None,
            'working_hours': 0.0,
            'net_working_hours': 0.0,
            'late_minutes': 0,
            'early_out_minutes': 0,
            'overtime_hours': 0.0,
            'shift': None,
            'shift_name': 'No Shift',
            'shift_source': 'None',
            'shift_start_time': None,
            'shift_end_time': None,
            'expected_start': None,
            'expected_end': None,
            'is_roster_day': False,
            'is_holiday': False,
            'is_leave': False,
            'holiday_name': None,
            'roster_info': None,
            'total_logs': 0,
            'expected_hours': getattr(employee, 'expected_working_hours', 8),
            'converted_from_late': False,
            'dynamic_shift_used': False,
            'shift_match_confidence': 0.0,
            'multiple_shifts_found': [],
            'break_time_minutes': 0,
            'overtime_break_minutes': 0,
            # New fields for enhanced rules
            'converted_from_minimum_hours': False,
            'converted_to_half_day': False,
            'converted_from_incomplete_punch': False,
            'excessive_working_hours_flag': False,
            'termination_risk_flag': False,
            'excessive_early_out_flag': False,
            'excessive_early_out': False,
            'flag_reason': None,
            'conversion_reason': None,
            'quality_score': 0,
        }
        
        # Check holidays first (highest priority)
        if holidays is None:
            holidays = Holiday.objects.filter(company=employee.company, date=attendance_date)
        
        holiday = holidays.filter(date=attendance_date).first()
        if holiday:
            record.update({
                'status': 'H',
                'original_status': 'H',
                'is_holiday': True,
                'holiday_name': holiday.name
            })
            
            # Process holiday attendance if logs exist
            if zk_logs and zk_logs.exists():
                self._process_holiday_attendance(record, zk_logs, employee)
            
            return record
        
        # Check leaves
        if leave_applications is None:
            leave_applications = LeaveApplication.objects.filter(
                employee=employee,
                status='A',  # Approved
                start_date__lte=attendance_date,
                end_date__gte=attendance_date
            )
        
        if leave_applications.filter(start_date__lte=attendance_date, end_date__gte=attendance_date).exists():
            record.update({
                'status': 'L',
                'original_status': 'L',
                'is_leave': True
            })
            return record
        
        # Check weekends
        if attendance_date.weekday() in self.weekend_days:
            record.update({
                'status': 'H',
                'original_status': 'H',
                'is_holiday': True,
                'holiday_name': f'{attendance_date.strftime("%A")} (Weekend)'
            })
            
            # Process weekend attendance if logs exist
            if zk_logs and zk_logs.exists():
                self._process_weekend_attendance(record, zk_logs, employee)
            
            return record
        
        # Process ZK logs for this date
        if zk_logs is None:
            zk_logs = AttendanceLog.objects.filter(
                employee=employee,
                timestamp__date=attendance_date
            ).order_by('timestamp')
        
        record['total_logs'] = zk_logs.count()
        
        if not zk_logs.exists():
            # No attendance logs - determine shift for absence analysis
            shift_info = self._get_shift_for_date(attendance_date, employee, roster_data)
            record.update(shift_info)
            return record
        
        # Process attendance logs
        sorted_logs = list(zk_logs.order_by('timestamp'))
        first_log = sorted_logs[0]
        last_log = sorted_logs[-1] if len(sorted_logs) > 1 else first_log
        
        record.update({
            'in_time': first_log.timestamp,
            'out_time': last_log.timestamp if len(sorted_logs) > 1 else None
        })
        
        # Dynamic Shift Detection vs Priority-based Detection
        if self.enable_dynamic_shift_detection:
            shift_info = self._detect_shift_dynamically(attendance_date, employee, record)
            record['dynamic_shift_used'] = True
        else:
            shift_info = self._get_shift_for_date(attendance_date, employee, roster_data)
        
        record.update(shift_info)
        
        # Calculate attendance metrics
        if record['shift'] and record['shift_start_time'] and record['shift_end_time']:
            self._calculate_attendance_metrics(record, employee)
        else:
            self._calculate_basic_attendance_metrics(record, employee)
        
        # Apply new rules
        record = self._apply_enhanced_rules(record)
        
        return record
    
    def _detect_shift_dynamically(self, date, employee, attendance_record):
        """Dynamic shift detection with fallback options."""
        
        if not attendance_record['in_time']:
            return self._get_fallback_shift_info(date, employee, "No check-in time for dynamic detection")
        
        # Get all available shifts
        all_shifts = Shift.objects.filter(company=employee.company)
        if not all_shifts.exists():
            return self._get_fallback_shift_info(date, employee, "No shifts configured in system")
        
        # Find matching shifts
        matching_shifts = []
        in_time = attendance_record['in_time'].time()
        out_time = attendance_record['out_time'].time() if attendance_record['out_time'] else None
        
        for shift in all_shifts:
            match_score = self._calculate_shift_match_score(shift, in_time, out_time)
            
            if match_score > 0:
                matching_shifts.append({
                    'shift': shift,
                    'score': match_score,
                    'confidence': min(match_score / 100, 1.0)
                })
        
        # Sort by score (highest first)
        matching_shifts.sort(key=lambda x: x['score'], reverse=True)
        
        if not matching_shifts:
            return self._get_fallback_shift_info(date, employee, "No shifts match the attendance pattern")
        
        if len(matching_shifts) > 1:
            # Apply priority logic for multiple matches
            best_shift = self._select_best_shift_from_matches(matching_shifts)
        else:
            best_shift = matching_shifts[0]
        
        return self._build_shift_info(
            shift=best_shift['shift'],
            source='DynamicDetection',
            roster_info=f"Dynamic Detection (Confidence: {best_shift['confidence']:.1%})",
            date=date,
            is_roster_day=False,
            additional_data={
                'shift_match_confidence': best_shift['confidence'],
                'multiple_shifts_found': [m['shift'].name for m in matching_shifts],
                'dynamic_shift_used': True,
            }
        )
    
    def _calculate_shift_match_score(self, shift, in_time, out_time=None):
        """Calculate how well attendance times match a shift."""
        
        score = 0
        tolerance = timedelta(minutes=self.dynamic_shift_tolerance_minutes)
        
        # Convert times to datetime for calculation
        base_date = datetime.now().date()
        shift_start = datetime.combine(base_date, shift.start_time)
        shift_end = datetime.combine(base_date, shift.end_time)
        
        # Handle overnight shifts
        if shift.end_time < shift.start_time:
            shift_end += timedelta(days=1)
        
        actual_start = datetime.combine(base_date, in_time)
        
        # Check in time match
        start_diff = abs((actual_start - shift_start).total_seconds())
        if start_diff <= tolerance.total_seconds():
            score += max(0, 50 - (start_diff / 60))
        
        # Check out time match (if available)
        if out_time:
            actual_end = datetime.combine(base_date, out_time)
            if out_time < in_time:  # Overnight attendance
                actual_end += timedelta(days=1)
            
            end_diff = abs((actual_end - shift_end).total_seconds())
            if end_diff <= tolerance.total_seconds():
                score += max(0, 50 - (end_diff / 60))
        else:
            score += 25 if score > 0 else 0
        
        return score
    
    def _select_best_shift_from_matches(self, matching_shifts):
        """Select the best shift when multiple matches are found."""
        
        if self.multiple_shift_priority == 'least_break':
            return min(matching_shifts, key=lambda x: getattr(x['shift'], 'break_time', 60))
        elif self.multiple_shift_priority == 'shortest_duration':
            return min(matching_shifts, key=lambda x: getattr(x['shift'], 'duration_minutes', 480))
        elif self.multiple_shift_priority == 'alphabetical':
            return min(matching_shifts, key=lambda x: x['shift'].name)
        else:
            return matching_shifts[0]
    
    def _get_shift_for_date(self, date, employee, roster_data=None):
        """Get shift with priority logic."""
        
        # Priority 1: Check roster data if provided
        if roster_data and 'days' in roster_data and date in roster_data['days']:
            roster_day = roster_data['days'][date]
            if roster_day.shift:
                return self._build_shift_info(
                    shift=roster_day.shift,
                    source='RosterDay',
                    roster_info=f"Roster Day: {roster_day.roster_assignment.roster.name}",
                    date=date,
                    is_roster_day=True
                )
        
        # Priority 2: Use employee's default shift
        if employee.default_shift:
            return self._build_shift_info(
                shift=employee.default_shift,
                source='Default',
                roster_info="Employee Default Shift",
                date=date,
                is_roster_day=False
            )
        
        # No shift found
        return self._get_no_shift_info("No Shift Assigned")
    
    def _build_shift_info(self, shift, source, roster_info, date, is_roster_day=False, additional_data=None):
        """Build comprehensive shift information dictionary."""
        
        try:
            expected_start = timezone.datetime.combine(date, shift.start_time)
            expected_start = timezone.make_aware(expected_start, timezone.get_default_timezone())
            
            expected_end = timezone.datetime.combine(date, shift.end_time)
            expected_end = timezone.make_aware(expected_end, timezone.get_default_timezone())
            
            # Handle overnight shifts
            if shift.end_time < shift.start_time:
                expected_end += timedelta(days=1)
            
            result = {
                'shift': shift,
                'shift_name': shift.name,
                'shift_source': source,
                'shift_start_time': shift.start_time,
                'shift_end_time': shift.end_time,
                'expected_start': expected_start,
                'expected_end': expected_end,
                'roster_info': roster_info,
                'is_roster_day': is_roster_day,
                'shift_break_time': getattr(shift, 'break_time', self.default_break_minutes),
            }
            
            if additional_data:
                result.update(additional_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error building shift info: {str(e)}")
            return self._get_no_shift_info(f"Error processing shift: {str(e)}")
    
    def _get_no_shift_info(self, reason="No shift available"):
        """Get default no-shift information."""
        return {
            'shift': None,
            'shift_name': 'No Shift',
            'shift_source': 'None',
            'shift_start_time': None,
            'shift_end_time': None,
            'expected_start': None,
            'expected_end': None,
            'roster_info': reason,
            'is_roster_day': False,
            'shift_break_time': self.default_break_minutes,
            'shift_match_confidence': 0.0,
            'multiple_shifts_found': [],
            'dynamic_shift_used': False
        }
    
    def _get_fallback_shift_info(self, date, employee, reason):
        """Get fallback shift when dynamic detection fails."""
        if self.dynamic_shift_fallback_to_default and employee.default_shift:
            return self._build_shift_info(
                shift=employee.default_shift,
                source='FallbackDefault',
                roster_info=f"Fallback to Default: {reason}",
                date=date,
                is_roster_day=False
            )
        elif self.dynamic_shift_fallback_shift_id:
            try:
                fallback_shift = Shift.objects.get(id=self.dynamic_shift_fallback_shift_id)
                return self._build_shift_info(
                    shift=fallback_shift,
                    source='FallbackFixed',
                    roster_info=f"Fallback to Fixed Shift: {reason}",
                    date=date,
                    is_roster_day=False
                )
            except Shift.DoesNotExist:
                pass
        
        return self._get_no_shift_info(reason)
    
    def _calculate_attendance_metrics(self, record, employee):
        """Calculate attendance metrics with enhanced rules."""
        
        shift = record['shift']
        in_time = record['in_time']
        out_time = record['out_time']
        expected_start = record['expected_start']
        expected_end = record['expected_end']
        
        # Get shift-specific or global grace time
        if self.use_shift_grace_time and hasattr(shift, 'grace_time') and shift.grace_time:
            grace_minutes = shift.grace_time
        else:
            grace_minutes = self._get_employee_setting(employee, 'overtime_grace_minutes', self.grace_minutes)
        
        # Check for late arrival
        if expected_start and grace_minutes is not None:
            late_threshold = expected_start + timedelta(minutes=grace_minutes)
            if in_time > late_threshold:
                late_duration = in_time - expected_start
                record['late_minutes'] = round(late_duration.total_seconds() / 60)
                record['status'] = 'LAT'
                record['original_status'] = 'LAT'
            else:
                record['status'] = 'P'
                record['original_status'] = 'P'
        else:
            record['status'] = 'P'
            record['original_status'] = 'P'
        
        # Calculate working hours
        if out_time:
            total_duration = out_time - in_time
            total_hours = total_duration.total_seconds() / 3600
            
            # Calculate break time
            break_minutes = self._calculate_break_time(record, total_hours)
            record['break_time_minutes'] = break_minutes
            
            working_hours = total_hours - (break_minutes / 60)
            record['working_hours'] = max(0, round(working_hours, 2))
            record['net_working_hours'] = record['working_hours']
        else:
            record['working_hours'] = 0
            record['net_working_hours'] = 0
            record['break_time_minutes'] = 0
        
        # Check for early departure
        if out_time and expected_end:
            early_threshold = expected_end - timedelta(minutes=self.early_out_threshold)
            if out_time < early_threshold:
                early_duration = expected_end - out_time
                record['early_out_minutes'] = round(early_duration.total_seconds() / 60)
        
        # Calculate overtime
        if out_time:
            overtime_info = self._calculate_overtime(record, employee, expected_start, expected_end)
            record.update(overtime_info)
        
        # Calculate quality score
        record['quality_score'] = self._calculate_quality_score(record)
    
    def _calculate_basic_attendance_metrics(self, record, employee):
        """Basic calculation without shift information."""
        
        record['status'] = 'P'
        record['original_status'] = 'P'
        
        if record['out_time']:
            duration = record['out_time'] - record['in_time']
            working_hours = duration.total_seconds() / 3600
            
            # Deduct default break time
            break_minutes = self.default_break_minutes
            working_hours = max(0, working_hours - (break_minutes / 60))
            
            record.update({
                'working_hours': round(working_hours, 2),
                'break_time_minutes': break_minutes,
                'net_working_hours': round(working_hours, 2),
            })
        
        record['quality_score'] = self._calculate_quality_score(record)
    
    def _calculate_break_time(self, record, total_hours):
        """Calculate break time based on configuration."""
        
        if self.use_shift_break_time and record['shift']:
            base_break = getattr(record['shift'], 'break_time', self.default_break_minutes)
        else:
            base_break = self.default_break_minutes
        
        if self.break_deduction_method == 'proportional':
            if total_hours <= 4:
                return base_break * 0.5
            elif total_hours <= 6:
                return base_break * 0.75
            else:
                return base_break
        else:
            return base_break
    
    def _calculate_overtime(self, record, employee, expected_start, expected_end):
        """Calculate overtime with multiple methods."""
        
        overtime_info = {
            'overtime_hours': 0.0,
            'overtime_break_minutes': 0,
            'overtime_calculation_method': self.overtime_calculation_method,
        }
        
        out_time = record['out_time']
        in_time = record['in_time']
        
        # Determine overtime start point
        if self.overtime_calculation_method == 'shift_based':
            if expected_end:
                overtime_start = expected_end + timedelta(minutes=self.overtime_start_after)
            else:
                return overtime_info
        else:
            overtime_start = in_time + timedelta(hours=employee.expected_working_hours) + timedelta(minutes=self.overtime_start_after)
        
        # Handle late arrival affecting overtime
        if self.late_affects_overtime and record['late_minutes'] > 0:
            overtime_start += timedelta(minutes=record['late_minutes'])
        
        # Calculate overtime duration
        if out_time > overtime_start:
            overtime_duration = out_time - overtime_start
            overtime_minutes = overtime_duration.total_seconds() / 60
            
            # Deduct separate OT break time
            if self.separate_ot_break_time > 0:
                overtime_minutes -= self.separate_ot_break_time
                overtime_info['overtime_break_minutes'] = self.separate_ot_break_time
            
            # Apply minimum overtime threshold
            if overtime_minutes >= self.minimum_overtime_minutes:
                overtime_info['overtime_hours'] = round(overtime_minutes / 60, 2)
        
        return overtime_info
    
    def _process_holiday_attendance(self, record, daily_logs, employee):
        """Process attendance on holidays."""
        
        sorted_logs = list(daily_logs.order_by('timestamp'))
        first_log = sorted_logs[0]
        last_log = sorted_logs[-1] if len(sorted_logs) > 1 else first_log
        
        record.update({
            'in_time': first_log.timestamp,
            'out_time': last_log.timestamp if len(sorted_logs) > 1 else None,
            'status': 'H',
        })
        
        if record['out_time'] and self.holiday_overtime_full_day:
            total_duration = record['out_time'] - record['in_time']
            total_hours = total_duration.total_seconds() / 3600
            
            break_minutes = self.default_break_minutes
            working_hours = total_hours - (break_minutes / 60)
            
            record.update({
                'working_hours': max(0, round(working_hours, 2)),
                'overtime_hours': max(0, round(working_hours, 2)),
                'break_time_minutes': break_minutes,
                'holiday_overtime': True,
            })
    
    def _process_weekend_attendance(self, record, daily_logs, employee):
        """Process attendance on weekends."""
        
        sorted_logs = list(daily_logs.order_by('timestamp'))
        first_log = sorted_logs[0]
        last_log = sorted_logs[-1] if len(sorted_logs) > 1 else first_log
        
        record.update({
            'in_time': first_log.timestamp,
            'out_time': last_log.timestamp if len(sorted_logs) > 1 else None,
            'status': 'H',
        })
        
        if record['out_time'] and self.weekend_overtime_full_day:
            total_duration = record['out_time'] - record['in_time']
            total_hours = total_duration.total_seconds() / 3600
            
            break_minutes = self.default_break_minutes
            working_hours = total_hours - (break_minutes / 60)
            
            record.update({
                'working_hours': max(0, round(working_hours, 2)),
                'overtime_hours': max(0, round(working_hours, 2)),
                'break_time_minutes': break_minutes,
                'weekend_overtime': True,
            })
    
    def _apply_enhanced_rules(self, record):
        """Apply enhanced attendance rules."""
        
        # Rule 1: Minimum Working Hours Rule
        if self.enable_minimum_working_hours_rule:
            record = self._apply_minimum_working_hours_rule(record)
        
        # Rule 2: Working Hours Half Day Rule
        if self.enable_working_hours_half_day_rule:
            record = self._apply_working_hours_half_day_rule(record)
        
        # Rule 3: Both In and Out Time Requirement
        if self.require_both_in_and_out:
            record = self._apply_both_in_out_rule(record)
        
        # Rule 4: Maximum Working Hours Rule
        if self.enable_maximum_working_hours_rule:
            record = self._apply_maximum_working_hours_rule(record)
        
        return record
    
    def _apply_minimum_working_hours_rule(self, record):
        """Apply minimum working hours rule."""
        if (record['status'] in ['P', 'LAT'] and 
            record['working_hours'] < self.minimum_working_hours_for_present):
            record['original_status'] = record['status']
            record['status'] = 'A'
            record['converted_from_minimum_hours'] = True
            record['conversion_reason'] = f'Working hours ({record["working_hours"]}h) less than minimum required ({self.minimum_working_hours_for_present}h)'
        return record
    
    def _apply_working_hours_half_day_rule(self, record):
        """Apply working hours based half day rule."""
        if (record['status'] in ['P', 'LAT'] and 
            self.half_day_minimum_hours <= record['working_hours'] < self.half_day_maximum_hours):
            record['original_status'] = record['status']
            record['status'] = 'HAL'
            record['converted_to_half_day'] = True
            record['conversion_reason'] = f'Working hours ({record["working_hours"]}h) qualifies for half day'
        return record
    
    def _apply_both_in_out_rule(self, record):
        """Apply both in-time and out-time requirement."""
        if (record['status'] in ['P', 'LAT'] and 
            (not record['in_time'] or not record['out_time'])):
            record['original_status'] = record['status']
            record['status'] = 'A'
            record['converted_from_incomplete_punch'] = True
            record['conversion_reason'] = 'Both check-in and check-out required'
        return record
    
    def _apply_maximum_working_hours_rule(self, record):
        """Apply maximum working hours rule."""
        if record['working_hours'] > self.maximum_allowable_working_hours:
            record['excessive_working_hours_flag'] = True
            record['flag_reason'] = f'Working hours ({record["working_hours"]}h) exceeds maximum allowed ({self.maximum_allowable_working_hours}h)'
            logger.warning(f"Excessive working hours detected: {record['working_hours']}h for employee {record['employee_id']} on {record['date']}")
        return record
    
    def _calculate_quality_score(self, record):
        """Calculate a quality score for the attendance record."""
        score = 0
        
        # Base score for having attendance data
        if record['total_logs'] > 0:
            score += 30
        
        # Score for having both check-in and check-out
        if record['in_time'] and record['out_time']:
            score += 40
        elif record['in_time']:
            score += 20
        
        # Score based on number of punches
        punch_score = min(record['total_logs'] * 5, 20)
        score += punch_score
        
        # Score for reasonable time patterns
        if record['in_time'] and record['out_time']:
            work_duration = record['working_hours']
            if 4 <= work_duration <= 12:  # Reasonable work duration
                score += 10
        
        return min(score, 100)
    
    def _get_employee_setting(self, employee, employee_attr, default_value):
        """Get employee-specific setting or fall back to default."""
        
        if hasattr(employee, employee_attr):
            employee_value = getattr(employee, employee_attr, None)
            if employee_value is not None:
                return employee_value
        
        return default_value
    
    def process_bulk_attendance(self, employees, start_date, end_date, company):
        """
        Process attendance for multiple employees over a date range.
        Returns a list of daily attendance records.
        """
        
        results = []
        
        # Get holidays for the date range
        holidays = Holiday.objects.filter(
            company=company,
            date__gte=start_date,
            date__lte=end_date
        )
        
        # Get leave applications for the date range
        leave_applications = LeaveApplication.objects.filter(
            employee__in=employees,
            status='A',  # Approved
            start_date__lte=end_date,
            end_date__gte=start_date
        ).select_related('employee')
        
        # Process each employee
        for employee in employees:
            current_date = start_date
            
            # Get employee's leave applications
            emp_leaves = leave_applications.filter(employee=employee)
            
            while current_date <= end_date:
                # Get attendance logs for this date
                zk_logs = AttendanceLog.objects.filter(
                    employee=employee,
                    timestamp__date=current_date
                ).order_by('timestamp')
                
                # Process the attendance
                record = self.process_employee_attendance(
                    employee=employee,
                    attendance_date=current_date,
                    zk_logs=zk_logs,
                    holidays=holidays,
                    leave_applications=emp_leaves,
                    roster_data=None  # Can be extended to include roster data
                )
                
                results.append(record)
                current_date += timedelta(days=1)
        
        return results
    
    def generate_attendance_summary(self, records):
        """Generate summary statistics from attendance records."""
        
        if not records:
            return {}
        
        summary = {
            'total_records': len(records),
            'total_employees': len(set(r['employee_id'] for r in records)),
            'present_count': 0,
            'absent_count': 0,
            'late_count': 0,
            'leave_count': 0,
            'holiday_count': 0,
            'half_day_count': 0,
            'total_working_hours': 0.0,
            'total_overtime_hours': 0.0,
            'avg_working_hours': 0.0,
            'attendance_percentage': 0.0,
            'punctuality_percentage': 0.0,
        }
        
        status_counts = defaultdict(int)
        total_hours = 0.0
        total_overtime = 0.0
        working_days = 0
        
        for record in records:
            status = record['status']
            status_counts[status] += 1
            
            if status in ['P', 'LAT', 'HAL']:
                total_hours += record['working_hours']
                total_overtime += record['overtime_hours']
                
            if status not in ['H', 'L']:  # Not holiday or leave
                working_days += 1
        
        summary.update({
            'present_count': status_counts.get('P', 0),
            'absent_count': status_counts.get('A', 0),
            'late_count': status_counts.get('LAT', 0),
            'leave_count': status_counts.get('L', 0),
            'holiday_count': status_counts.get('H', 0),
            'half_day_count': status_counts.get('HAL', 0),
            'total_working_hours': round(total_hours, 2),
            'total_overtime_hours': round(total_overtime, 2),
        })
        
        # Calculate averages and percentages
        if len(records) > 0:
            summary['avg_working_hours'] = round(total_hours / len(records), 2)
        
        if working_days > 0:
            attended_days = summary['present_count'] + summary['late_count'] + (summary['half_day_count'] * 0.5)
            summary['attendance_percentage'] = round((attended_days / working_days) * 100, 2)
            summary['punctuality_percentage'] = round((summary['present_count'] / working_days) * 100, 2)
        
        return summary