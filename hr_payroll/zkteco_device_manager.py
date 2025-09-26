# zkteco_device_manager.py
import logging
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

logger = logging.getLogger(__name__)

try:
    from zk import ZK
    from zk.exception import ZKNetworkError, ZKErrorResponse
    ZK_AVAILABLE = True
except ImportError:
    ZK_AVAILABLE = False
    logger.warning("ZK library not available. Please install it with 'pip install pyzk'")

class ZKTecoDeviceManager:
    """
    ZKTeco device manager for handling multiple devices
    with connection testing, data fetching, and attendance management
    NO USER DEPENDENCY - only handles device connections and data
    """
    
    def __init__(self):
        self.connections = {}
        self.connection_status = {}
        self.connection_lock = threading.Lock()
        
    def connect_device(self, device_ip, device_port=4370, password=0, timeout=30):
        """Connect to a single ZKTeco device with enhanced error handling"""
        try:
            if not ZK_AVAILABLE:
                return False, "ZK library not available. Please install pyzk."
            
            # Try multiple connection methods
            connection_methods = [
                {'force_udp': False, 'ommit_ping': False},
                {'force_udp': True, 'ommit_ping': False},
                {'force_udp': False, 'ommit_ping': True},
                {'force_udp': True, 'ommit_ping': True},
            ]
            
            last_error = None
            
            for method in connection_methods:
                try:
                    zk = ZK(
                        device_ip, 
                        port=device_port, 
                        timeout=timeout, 
                        password=password,
                        force_udp=method['force_udp'],
                        ommit_ping=method['ommit_ping']
                    )
                    
                    conn = zk.connect()
                    
                    if conn:
                        # Test connection by getting basic info
                        try:
                            device_info = self._get_device_info(conn)
                            
                            with self.connection_lock:
                                self.connections[device_ip] = conn
                                self.connection_status[device_ip] = {
                                    'status': 'connected',
                                    'info': device_info,
                                    'last_connected': datetime.now(),
                                    'connection_method': method
                                }
                            
                            logger.info(f"Successfully connected to device {device_ip} using method: {method}")
                            return True, device_info
                            
                        except Exception as info_error:
                            conn.disconnect()
                            last_error = f"Connected but failed to get device info: {str(info_error)}"
                            continue
                            
                except Exception as e:
                    last_error = str(e)
                    continue
            
            # All connection methods failed
            with self.connection_lock:
                self.connection_status[device_ip] = {
                    'status': 'failed',
                    'error': last_error,
                    'last_attempt': datetime.now()
                }
            
            logger.error(f"Failed to connect to device {device_ip}: {last_error}")
            return False, last_error
            
        except Exception as e:
            error_msg = f"Unexpected error connecting to device {device_ip}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def _get_device_info(self, conn):
        """Get comprehensive device information"""
        try:
            device_info = {}
            
            # Basic device information
            try:
                device_info['firmware_version'] = conn.get_firmware_version()
            except:
                device_info['firmware_version'] = 'Unknown'
            
            try:
                device_info['serialnumber'] = conn.get_serialnumber()
            except:
                device_info['serialnumber'] = 'Unknown'
            
            try:
                device_info['platform'] = conn.get_platform()
            except:
                device_info['platform'] = 'Unknown'
            
            try:
                device_info['device_name'] = conn.get_device_name()
            except:
                device_info['device_name'] = 'Unknown'
            
            try:
                device_info['time'] = conn.get_time()
            except:
                device_info['time'] = 'Unknown'
            
            # Get user count
            try:
                users = conn.get_users()
                device_info['user_count'] = len(users)
            except:
                device_info['user_count'] = 0
            
            # Get attendance counts (no user data needed for device list)
            try:
                attendances = conn.get_attendance()
                device_info['attendance_count'] = len(attendances)
                
                # Get latest attendance
                if attendances:
                    latest_attendance = max(attendances, key=lambda x: x.timestamp)
                    device_info['latest_attendance'] = {
                        'timestamp': latest_attendance.timestamp,
                        'user_id': latest_attendance.user_id
                    }
                else:
                    device_info['latest_attendance'] = None
            except Exception as e:
                device_info['attendance_count'] = 0
                device_info['latest_attendance'] = None
                logger.warning(f"Could not get attendance data: {str(e)}")
            
            return device_info
            
        except Exception as e:
            logger.error(f"Error getting device info: {str(e)}")
            return {'error': str(e)}
    
    def test_multiple_connections(self, device_list, max_workers=5):
        """Test connections to multiple devices concurrently"""
        if not ZK_AVAILABLE:
            return {device['ip']: {'success': False, 'error': 'ZK library not available'} for device in device_list}
        
        results = {}
        
        def test_single_device(device_data):
            device_ip = device_data['ip']
            device_port = device_data.get('port', 4370)
            password = device_data.get('password', 0)
            
            success, info = self.connect_device(device_ip, device_port, password)
            return device_ip, success, info
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_device = {
                executor.submit(test_single_device, device): device 
                for device in device_list
            }
            
            for future in as_completed(future_to_device):
                try:
                    device_ip, success, info = future.result()
                    results[device_ip] = {
                        'success': success,
                        'info': info if success else None,
                        'error': info if not success else None
                    }
                except Exception as e:
                    device = future_to_device[future]
                    results[device['ip']] = {
                        'success': False,
                        'info': None,
                        'error': f"Execution error: {str(e)}"
                    }
        
        return results
    
    def get_users_data(self, device_ip):
        """Fetch user data from a specific device"""
        try:
            if not ZK_AVAILABLE:
                return False, "ZK library not available"
            
            if device_ip not in self.connections:
                success, error = self.connect_device(device_ip)
                if not success:
                    return False, f"Device not connected: {error}"
            
            conn = self.connections[device_ip]
            
            # Verify connection is still active
            try:
                conn.get_time()  # Simple test to verify connection
            except:
                # Reconnect if connection is lost
                success, error = self.connect_device(device_ip)
                if not success:
                    return False, f"Failed to reconnect: {error}"
                conn = self.connections[device_ip]
            
            users = conn.get_users()
            
            users_data = []
            for user in users:
                user_dict = {
                    'user_id': str(user.user_id),
                    'name': user.name or f'User_{user.user_id}',
                    'privilege': getattr(user, 'privilege', 0),
                    'password': getattr(user, 'password', ''),
                    'group_id': getattr(user, 'group_id', ''),
                    'card': getattr(user, 'card', 0),
                    'device_ip': device_ip
                }
                users_data.append(user_dict)
            
            logger.info(f"Fetched {len(users_data)} users from {device_ip}")
            return True, users_data
            
        except Exception as e:
            error_msg = f"Error fetching users from {device_ip}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def get_multiple_users_data(self, device_list, max_workers=3):
        """Fetch user data from multiple devices concurrently"""
        if not ZK_AVAILABLE:
            return [], [{'device': {'name': device['name']}, 'success': False, 'error': 'ZK library not available'} for device in device_list]
        
        all_users_data = []
        results = []
        
        def fetch_users_from_device(device_data):
            device_ip = device_data['ip']
            device_name = device_data.get('name', device_ip)
            device_port = device_data.get('port', 4370)
            password = device_data.get('password', 0)
            
            # Ensure connection
            if device_ip not in self.connections:
                success, _ = self.connect_device(device_ip, device_port, password)
                if not success:
                    return device_ip, device_name, False, "Failed to connect"
            
            success, data = self.get_users_data(device_ip)
            
            if success:
                # Add device name to each user record
                for user in data:
                    user['device_name'] = device_name
                
            return device_ip, device_name, success, data
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_device = {
                executor.submit(fetch_users_from_device, device): device 
                for device in device_list
            }
            
            for future in as_completed(future_to_device):
                try:
                    device_ip, device_name, success, data = future.result()
                    
                    results.append({
                        'device': {'name': device_name, 'ip': device_ip},
                        'success': success,
                        'users_found': len(data) if success else 0,
                        'error': data if not success else None
                    })
                    
                    if success:
                        all_users_data.extend(data)
                        
                except Exception as e:
                    device = future_to_device[future]
                    results.append({
                        'device': {'name': device.get('name', device['ip'])},
                        'success': False,
                        'users_found': 0,
                        'error': f"Execution error: {str(e)}"
                    })
        
        return all_users_data, results
    
    def get_attendance_data(self, device_ip, start_date=None, end_date=None, limit=None):
        """Fetch attendance data from a specific device with enhanced filtering"""
        try:
            if not ZK_AVAILABLE:
                return False, "ZK library not available"
            
            if device_ip not in self.connections:
                # Try to connect if not already connected
                success, error = self.connect_device(device_ip)
                if not success:
                    return False, f"Failed to connect to device {device_ip}: {error}"
            
            conn = self.connections[device_ip]
            
            # Verify connection is still active
            try:
                conn.get_time()  # Simple test to verify connection
            except:
                # Reconnect if connection is lost
                success, error = self.connect_device(device_ip)
                if not success:
                    return False, f"Failed to reconnect: {error}"
                conn = self.connections[device_ip]
            
            # Get all attendance records
            attendances = conn.get_attendance()
            
            attendance_data = []
            for attendance in attendances:
                # Apply date filtering
                attendance_date = attendance.timestamp.date()
                
                if start_date and attendance_date < start_date:
                    continue
                if end_date and attendance_date > end_date:
                    continue
                
                attendance_dict = {
                    'zkteco_id': str(attendance.user_id),
                    'timestamp': attendance.timestamp,
                    'source_type': 'device',
                    'device_ip': device_ip,
                    'punch_type': getattr(attendance, 'punch', 0),
                    'verify_type': getattr(attendance, 'status', 0),
                }
                attendance_data.append(attendance_dict)
            
            # Sort by timestamp (newest first)
            attendance_data.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Apply limit if specified
            if limit:
                attendance_data = attendance_data[:limit]
            
            logger.info(f"Fetched {len(attendance_data)} attendance records from {device_ip}")
            return True, attendance_data
            
        except Exception as e:
            error_msg = f"Error fetching attendance from {device_ip}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_multiple_attendance_data(self, device_list, start_date=None, end_date=None, max_workers=3):
        """Fetch attendance data from multiple devices concurrently"""
        if not ZK_AVAILABLE:
            return [], [{'device': {'name': device['name']}, 'success': False, 'error': 'ZK library not available'} for device in device_list]
        
        all_attendance_data = []
        results = []
        
        def fetch_from_device(device_data):
            device_ip = device_data['ip']
            device_name = device_data.get('name', device_ip)
            device_port = device_data.get('port', 4370)
            password = device_data.get('password', 0)
            
            # Ensure connection
            if device_ip not in self.connections:
                success, _ = self.connect_device(device_ip, device_port, password)
                if not success:
                    return device_ip, device_name, False, "Failed to connect"
            
            success, data = self.get_attendance_data(device_ip, start_date, end_date)
            
            if success:
                # Add device name to each record
                for record in data:
                    record['device_name'] = device_name
                
            return device_ip, device_name, success, data
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_device = {
                executor.submit(fetch_from_device, device): device 
                for device in device_list
            }
            
            for future in as_completed(future_to_device):
                try:
                    device_ip, device_name, success, data = future.result()
                    
                    results.append({
                        'device': {'name': device_name, 'ip': device_ip},
                        'success': success,
                        'records_found': len(data) if success else 0,
                        'error': data if not success else None
                    })
                    
                    if success:
                        all_attendance_data.extend(data)
                        
                except Exception as e:
                    device = future_to_device[future]
                    results.append({
                        'device': {'name': device.get('name', device['ip'])},
                        'success': False,
                        'records_found': 0,
                        'error': f"Execution error: {str(e)}"
                    })
        
        # Sort all attendance data by timestamp (newest first)
        all_attendance_data.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return all_attendance_data, results
    
    def disconnect_device(self, device_ip):
        """Disconnect from a specific device"""
        try:
            with self.connection_lock:
                if device_ip in self.connections:
                    self.connections[device_ip].disconnect()
                    del self.connections[device_ip]
                    if device_ip in self.connection_status:
                        self.connection_status[device_ip]['status'] = 'disconnected'
                        self.connection_status[device_ip]['disconnected_at'] = datetime.now()
            logger.info(f"Disconnected from device {device_ip}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from {device_ip}: {str(e)}")
            return False
    
    def disconnect_all(self):
        """Disconnect from all connected devices"""
        disconnected_count = 0
        with self.connection_lock:
            device_ips = list(self.connections.keys())
        
        for device_ip in device_ips:
            if self.disconnect_device(device_ip):
                disconnected_count += 1
        
        logger.info(f"Disconnected from {disconnected_count} devices")
        return disconnected_count
    
    def get_connection_status(self, device_ip=None):
        """Get connection status for specific device or all devices"""
        with self.connection_lock:
            if device_ip:
                return self.connection_status.get(device_ip, {'status': 'unknown'})
            return self.connection_status.copy()
    
    def clear_attendance_data(self, device_ip):
        """Clear attendance data from device"""
        try:
            if not ZK_AVAILABLE:
                return False, "ZK library not available"
            
            if device_ip not in self.connections:
                success, error = self.connect_device(device_ip)
                if not success:
                    return False, f"Device not connected: {error}"
            
            conn = self.connections[device_ip]
            conn.clear_attendance()
            logger.info(f"Cleared attendance data from {device_ip}")
            return True, "Attendance data cleared successfully"
            
        except Exception as e:
            error_msg = f"Error clearing attendance from {device_ip}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg