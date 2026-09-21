import json
from typing import Callable, Optional

from .repository import IpamRepository


class IpamServiceError(ValueError):
    pass


class IpamService:
    def __init__(self, repository: IpamRepository, user_lookup: Optional[Callable[[int], object]] = None):
        self.repository = repository
        self._user_lookup = user_lookup

    def translate_value_error(self, operation: Callable, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except ValueError as exc:
            raise IpamServiceError(str(exc)) from exc

    def get_user_by_id(self, user_id: int):
        return self._user_lookup(user_id) if self._user_lookup else None

    def get_username(self, user_id: int):
        user = self.get_user_by_id(user_id)
        return user["username"] if user else None

    @property
    def SCAN_CONCURRENCY_MIN(self):
        return self.repository.scan_concurrency_min

    @property
    def SCAN_CONCURRENCY_MAX(self):
        return self.repository.scan_concurrency_max


    def add_address(self, *args, **kwargs):
        return self.translate_value_error(self.repository.add_address, *args, **kwargs)

    def add_address_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.add_address_tag, *args, **kwargs)

    def add_dhcp_pool(self, *args, **kwargs):
        return self.translate_value_error(self.repository.add_dhcp_pool, *args, **kwargs)

    def add_scan_exclude(self, *args, **kwargs):
        return self.translate_value_error(self.repository.add_scan_exclude, *args, **kwargs)

    def add_subnet_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.add_subnet_tag, *args, **kwargs)

    def apply_scan_result(self, *args, **kwargs):
        return self.translate_value_error(self.repository.apply_scan_result, *args, **kwargs)

    def bulk_delete_addresses(self, *args, **kwargs):
        return self.translate_value_error(self.repository.bulk_delete_addresses, *args, **kwargs)

    def bulk_move_addresses(self, *args, **kwargs):
        return self.translate_value_error(self.repository.bulk_move_addresses, *args, **kwargs)

    def bulk_move_dhcp_pools(self, *args, **kwargs):
        return self.translate_value_error(self.repository.bulk_move_dhcp_pools, *args, **kwargs)

    def bulk_update_addresses(self, *args, **kwargs):
        return self.translate_value_error(self.repository.bulk_update_addresses, *args, **kwargs)

    def cleanup_scan_jobs(self, *args, **kwargs):
        return self.translate_value_error(self.repository.cleanup_scan_jobs, *args, **kwargs)

    def create_scan_job(self, *args, **kwargs):
        return self.translate_value_error(self.repository.create_scan_job, *args, **kwargs)

    def create_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.create_subnet, *args, **kwargs)

    def create_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.create_tag, *args, **kwargs)

    def delete_address(self, *args, **kwargs):
        return self.translate_value_error(self.repository.delete_address, *args, **kwargs)

    def delete_dhcp_pool(self, *args, **kwargs):
        return self.translate_value_error(self.repository.delete_dhcp_pool, *args, **kwargs)

    def delete_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.delete_subnet, *args, **kwargs)

    def delete_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.delete_tag, *args, **kwargs)

    def expire_timed_out_scan_jobs(self, *args, **kwargs):
        return self.translate_value_error(self.repository.expire_timed_out_scan_jobs, *args, **kwargs)

    def export_audit_log_csv(self, *args, **kwargs):
        return self.translate_value_error(self.repository.export_audit_log_csv, *args, **kwargs)

    def query_audit_log(self, *args, **kwargs):
        page = self.translate_value_error(self.repository.query_audit_log, *args, **kwargs)
        entries = []
        for row in page["entries"]:
            entries.append({
                "id": row["id"],
                "addressId": row["address_id"],
                "subnetId": row["subnet_id"],
                "dhcpPoolId": row["dhcp_pool_id"],
                "userId": row["user_id"],
                "username": self.get_username(row["user_id"]) if row["user_id"] else None,
                "changeType": row["change_type"],
                "oldValue": json.loads(row["old_value"]) if row["old_value"] else None,
                "newValue": json.loads(row["new_value"]) if row["new_value"] else None,
                "description": row["description"],
                "ipAddress": row["ip_address"],
                "subnetCidr": row["subnet_cidr"],
                "createdAt": row["created_at"],
            })
        return {**page, "entries": entries}

    def find_next_contiguous_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.find_next_contiguous_subnet, *args, **kwargs)

    def get_active_scan_job(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_active_scan_job, *args, **kwargs)

    def get_address_audit_log(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_address_audit_log, *args, **kwargs)

    def get_address_tags(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_address_tags, *args, **kwargs)

    def get_addresses_by_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_addresses_by_subnet, *args, **kwargs)

    def get_addresses_by_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_addresses_by_tag, *args, **kwargs)

    def get_dhcp_pools(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_dhcp_pools, *args, **kwargs)

    def get_ipam_dashboard(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_ipam_dashboard, *args, **kwargs)

    def get_next_available_ip(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_next_available_ip, *args, **kwargs)

    def get_scan_concurrency_limit(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_scan_concurrency_limit, *args, **kwargs)

    def get_scan_job(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_scan_job, *args, **kwargs)

    def get_scan_schedule(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_scan_schedule, *args, **kwargs)

    def get_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_subnet, *args, **kwargs)

    def get_subnet_address(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_subnet_address, *args, **kwargs)

    def get_subnet_audit_log(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_subnet_audit_log, *args, **kwargs)

    def get_subnet_tags(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_subnet_tags, *args, **kwargs)

    def get_subnets_by_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_subnets_by_tag, *args, **kwargs)

    def get_tags(self, *args, **kwargs):
        return self.translate_value_error(self.repository.get_tags, *args, **kwargs)

    def is_scan_job_cancel_requested(self, *args, **kwargs):
        return self.translate_value_error(self.repository.is_scan_job_cancel_requested, *args, **kwargs)

    def list_due_scan_schedules(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_due_scan_schedules, *args, **kwargs)

    def list_misplaced_addresses(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_misplaced_addresses, *args, **kwargs)

    def list_misplaced_dhcp_pools(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_misplaced_dhcp_pools, *args, **kwargs)

    def list_scan_excludes(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_scan_excludes, *args, **kwargs)

    def list_scan_excludes_detailed(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_scan_excludes_detailed, *args, **kwargs)

    def list_scans(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_scans, *args, **kwargs)

    def list_subnet_addresses(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_subnet_addresses, *args, **kwargs)

    def list_subnets(self, *args, **kwargs):
        return self.translate_value_error(self.repository.list_subnets, *args, **kwargs)

    def mark_scan_schedule_started(self, *args, **kwargs):
        return self.translate_value_error(self.repository.mark_scan_schedule_started, *args, **kwargs)

    def move_address(self, *args, **kwargs):
        return self.translate_value_error(self.repository.move_address, *args, **kwargs)

    def move_dhcp_pool(self, *args, **kwargs):
        return self.translate_value_error(self.repository.move_dhcp_pool, *args, **kwargs)

    def record_scan(self, *args, **kwargs):
        return self.translate_value_error(self.repository.record_scan, *args, **kwargs)

    def remove_address_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.remove_address_tag, *args, **kwargs)

    def remove_scan_exclude_by_id(self, *args, **kwargs):
        return self.translate_value_error(self.repository.remove_scan_exclude_by_id, *args, **kwargs)

    def remove_subnet_tag(self, *args, **kwargs):
        return self.translate_value_error(self.repository.remove_subnet_tag, *args, **kwargs)

    def request_scan_job_cancel(self, *args, **kwargs):
        return self.translate_value_error(self.repository.request_scan_job_cancel, *args, **kwargs)

    def search_addresses(self, *args, **kwargs):
        return self.translate_value_error(self.repository.search_addresses, *args, **kwargs)

    def search_tags(self, *args, **kwargs):
        return self.translate_value_error(self.repository.search_tags, *args, **kwargs)

    def set_scan_concurrency_limit(self, *args, **kwargs):
        return self.translate_value_error(self.repository.set_scan_concurrency_limit, *args, **kwargs)

    def subnet_exists(self, *args, **kwargs):
        return self.translate_value_error(self.repository.subnet_exists, *args, **kwargs)

    def update_address(self, *args, **kwargs):
        return self.translate_value_error(self.repository.update_address, *args, **kwargs)

    def update_dhcp_pool(self, *args, **kwargs):
        return self.translate_value_error(self.repository.update_dhcp_pool, *args, **kwargs)

    def update_scan_job(self, *args, **kwargs):
        return self.translate_value_error(self.repository.update_scan_job, *args, **kwargs)

    def update_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.update_subnet, *args, **kwargs)

    def upsert_scan_schedule(self, *args, **kwargs):
        return self.translate_value_error(self.repository.upsert_scan_schedule, *args, **kwargs)

    def validate_address_in_subnet(self, *args, **kwargs):
        return self.translate_value_error(self.repository.validate_address_in_subnet, *args, **kwargs)
