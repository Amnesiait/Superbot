import hashlib
import uuid
import platform
import logging
import os
import json
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger("Security")

class LicenseManager:
    """
    Commercial License Enforcement System.
    Binds the application to specific hardware to prevent piracy.
    """
    
    def __init__(self):
        self._machine_id = self._generate_machine_id()
        self._license_file = "license.key"
        self._public_key = None # In real commercial version, this would be a hardcoded RSA public key
        
    def _generate_machine_id(self) -> str:
        """
        Generate a unique, stable fingerprint for this machine.
        Combines Node Name, Machine Name, Processor, and System details.
        """
        components = [
            platform.node(),
            platform.machine(),
            platform.processor(),
            platform.system(),
            str(uuid.getnode()) # MAC address based
        ]
        
        fingerprint_raw = "|".join(filter(None, components))
        # Create a SHA-256 hash of the fingerprint
        return hashlib.sha256(fingerprint_raw.encode()).hexdigest().upper()[:32]

    def get_hardware_id(self) -> str:
        """Return the unique Hardware ID for this machine (for user to send to support)."""
        # Format as XXXX-XXXX-XXXX-XXXX for readability
        raw = self._machine_id
        return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

    def validate_license(self) -> bool:
        """
        Check if a valid license exists for this specific machine.
        Returns True if authorized, False otherwise.
        """
        if not os.path.exists(self._license_file):
            logger.error(f"[SECURITY] No license file found ({self._license_file})")
            logger.info(f"[SECURITY] Please contact support with your Hardware ID: {self.get_hardware_id()}")
            return False
            
        try:
            with open(self._license_file, 'r') as f:
                data = json.load(f)
                
            # 1. Check Hardware Binding
            license_hw_id = data.get('hardware_id')
            if license_hw_id != self.get_hardware_id():
                logger.critical("[SECURITY] LICENSE VIOLATION: Hardware ID mismatch!")
                logger.critical(f"[SECURITY] License bound to: {license_hw_id}")
                logger.critical(f"[SECURITY] Current Machine:  {self.get_hardware_id()}")
                return False
                
            # 2. Check Expiry
            expiry_str = data.get('expiry_date') # YYYY-MM-DD
            if expiry_str != "LIFETIME":
                expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
                if datetime.now() > expiry:
                    logger.critical(f"[SECURITY] LICENSE EXPIRED on {expiry_str}")
                    return False
            
            # 3. Check Signature (Simplified for demo, would use RSA/Ed25519 in prod)
            # In a real app, we would verify data['signature'] using self._public_key
            # and the content of the license.
            
            logger.info(f"[SECURITY] License verified. Type: {data.get('type', 'TRIAL')}. Owner: {data.get('owner', 'Unknown')}")
            return True
            
        except json.JSONDecodeError:
            logger.error("[SECURITY] Corrupt license file.")
            return False
        except Exception as e:
            logger.error(f"[SECURITY] Validation error: {e}")
            return False

    def create_trial_license(self, owner_name: str = "Trial User") -> None:
        """
        Helper to generate a trial license for THIS machine (Dev/Testing only).
        REMOVE THIS METHOD IN PRODUCTION BUILD.
        """
        import json
        
        # Create a license active for 30 days
        license_data = {
            "hardware_id": self.get_hardware_id(),
            "owner": owner_name,
            "type": "TRIAL",
            "expiry_date": "LIFETIME", # For easier testing
            "features": ["ALL"],
            "signature": "DEV_SIGNATURE_PLACEHOLDER"
        }
        
        with open(self._license_file, 'w') as f:
            json.dump(license_data, f, indent=4)
            
        logger.info(f"[SECURITY] Generated TRIAL license for {self.get_hardware_id()}")

# Global Instance
_license_mgr = LicenseManager()

def enforce_license():
    """Blocking call to enforce license. Exits if invalid."""
    if not _license_mgr.validate_license():
        logger.critical("==================================================")
        logger.critical("             ACCESS DENIED                        ")
        logger.critical("   This software is protected by AETHER Security  ")
        logger.critical(f"   Hardware ID: {_license_mgr.get_hardware_id()} ")
        logger.critical("==================================================")
        # In production, we might want to initiate a shutdown or return False
        # For now, we return False so the caller can handle exit gracefully
        return False
    return True
