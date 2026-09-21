from types import ModuleType


class IpamRepository:
    def __init__(self, database: ModuleType):
        self._db = database

    @property
    def scan_concurrency_min(self):
        return self._db.SCAN_CONCURRENCY_MIN

    @property
    def scan_concurrency_max(self):
        return self._db.SCAN_CONCURRENCY_MAX

    @property
    def scan_job_timeout_seconds(self):
        return self._db.SCAN_JOB_TIMEOUT_SECONDS

    def add_address(self, *args, **kwargs):
        return self._db.add_address(*args, **kwargs)

    def add_address_tag(self, *args, **kwargs):
        return self._db.add_address_tag(*args, **kwargs)

    def add_dhcp_pool(self, *args, **kwargs):
        return self._db.add_dhcp_pool(*args, **kwargs)

    def add_scan_exclude(self, *args, **kwargs):
        return self._db.add_scan_exclude(*args, **kwargs)

    def add_subnet_tag(self, *args, **kwargs):
        return self._db.add_subnet_tag(*args, **kwargs)

    def apply_scan_result(self, *args, **kwargs):
        return self._db.apply_scan_result(*args, **kwargs)

    def bulk_delete_addresses(self, *args, **kwargs):
        return self._db.bulk_delete_addresses(*args, **kwargs)

    def bulk_move_addresses(self, *args, **kwargs):
        return self._db.bulk_move_addresses(*args, **kwargs)

    def bulk_move_dhcp_pools(self, *args, **kwargs):
        return self._db.bulk_move_dhcp_pools(*args, **kwargs)

    def bulk_update_addresses(self, *args, **kwargs):
        return self._db.bulk_update_addresses(*args, **kwargs)

    def cleanup_scan_jobs(self, *args, **kwargs):
        return self._db.cleanup_scan_jobs(*args, **kwargs)

    def create_scan_job(self, *args, **kwargs):
        return self._db.create_scan_job(*args, **kwargs)

    def create_subnet(self, *args, **kwargs):
        return self._db.create_subnet(*args, **kwargs)

    def create_tag(self, *args, **kwargs):
        return self._db.create_tag(*args, **kwargs)

    def delete_address(self, *args, **kwargs):
        return self._db.delete_address(*args, **kwargs)

    def delete_dhcp_pool(self, *args, **kwargs):
        return self._db.delete_dhcp_pool(*args, **kwargs)

    def delete_subnet(self, *args, **kwargs):
        return self._db.delete_subnet(*args, **kwargs)

    def delete_tag(self, *args, **kwargs):
        return self._db.delete_tag(*args, **kwargs)

    def expire_timed_out_scan_jobs(self, *args, **kwargs):
        return self._db.expire_timed_out_scan_jobs(*args, **kwargs)

    def export_audit_log_csv(self, *args, **kwargs):
        return self._db.export_audit_log_csv(*args, **kwargs)

    def query_audit_log(self, *args, **kwargs):
        return self._db.query_audit_log(*args, **kwargs)

    def find_next_contiguous_subnet(self, *args, **kwargs):
        return self._db.find_next_contiguous_subnet(*args, **kwargs)

    def get_active_scan_job(self, *args, **kwargs):
        return self._db.get_active_scan_job(*args, **kwargs)

    def get_address_audit_log(self, *args, **kwargs):
        return self._db.get_address_audit_log(*args, **kwargs)

    def get_address_tags(self, *args, **kwargs):
        return self._db.get_address_tags(*args, **kwargs)

    def get_addresses_by_subnet(self, *args, **kwargs):
        return self._db.get_addresses_by_subnet(*args, **kwargs)

    def get_addresses_by_tag(self, *args, **kwargs):
        return self._db.get_addresses_by_tag(*args, **kwargs)

    def get_dhcp_pools(self, *args, **kwargs):
        return self._db.get_dhcp_pools(*args, **kwargs)

    def get_ipam_dashboard(self, *args, **kwargs):
        return self._db.get_ipam_dashboard(*args, **kwargs)

    def get_next_available_ip(self, *args, **kwargs):
        return self._db.get_next_available_ip(*args, **kwargs)

    def get_scan_concurrency_limit(self, *args, **kwargs):
        return self._db.get_scan_concurrency_limit(*args, **kwargs)

    def get_scan_job(self, *args, **kwargs):
        return self._db.get_scan_job(*args, **kwargs)

    def get_scan_schedule(self, *args, **kwargs):
        return self._db.get_scan_schedule(*args, **kwargs)

    def get_subnet(self, *args, **kwargs):
        return self._db.get_subnet(*args, **kwargs)

    def get_subnet_address(self, *args, **kwargs):
        return self._db.get_subnet_address(*args, **kwargs)

    def get_subnet_audit_log(self, *args, **kwargs):
        return self._db.get_subnet_audit_log(*args, **kwargs)

    def get_subnet_tags(self, *args, **kwargs):
        return self._db.get_subnet_tags(*args, **kwargs)

    def get_subnets_by_tag(self, *args, **kwargs):
        return self._db.get_subnets_by_tag(*args, **kwargs)

    def get_tags(self, *args, **kwargs):
        return self._db.get_tags(*args, **kwargs)

    def is_scan_job_cancel_requested(self, *args, **kwargs):
        return self._db.is_scan_job_cancel_requested(*args, **kwargs)

    def list_due_scan_schedules(self, *args, **kwargs):
        return self._db.list_due_scan_schedules(*args, **kwargs)

    def list_misplaced_addresses(self, *args, **kwargs):
        return self._db.list_misplaced_addresses(*args, **kwargs)

    def list_misplaced_dhcp_pools(self, *args, **kwargs):
        return self._db.list_misplaced_dhcp_pools(*args, **kwargs)

    def list_scan_excludes(self, *args, **kwargs):
        return self._db.list_scan_excludes(*args, **kwargs)

    def list_scan_excludes_detailed(self, *args, **kwargs):
        return self._db.list_scan_excludes_detailed(*args, **kwargs)

    def list_scans(self, *args, **kwargs):
        return self._db.list_scans(*args, **kwargs)

    def list_subnet_addresses(self, *args, **kwargs):
        return self._db.list_subnet_addresses(*args, **kwargs)

    def list_subnets(self, *args, **kwargs):
        return self._db.list_subnets(*args, **kwargs)

    def mark_scan_schedule_started(self, *args, **kwargs):
        return self._db.mark_scan_schedule_started(*args, **kwargs)

    def move_address(self, *args, **kwargs):
        return self._db.move_address(*args, **kwargs)

    def move_dhcp_pool(self, *args, **kwargs):
        return self._db.move_dhcp_pool(*args, **kwargs)

    def record_scan(self, *args, **kwargs):
        return self._db.record_scan(*args, **kwargs)

    def remove_address_tag(self, *args, **kwargs):
        return self._db.remove_address_tag(*args, **kwargs)

    def remove_scan_exclude_by_id(self, *args, **kwargs):
        return self._db.remove_scan_exclude_by_id(*args, **kwargs)

    def remove_subnet_tag(self, *args, **kwargs):
        return self._db.remove_subnet_tag(*args, **kwargs)

    def request_scan_job_cancel(self, *args, **kwargs):
        return self._db.request_scan_job_cancel(*args, **kwargs)

    def search_addresses(self, *args, **kwargs):
        return self._db.search_addresses(*args, **kwargs)

    def search_tags(self, *args, **kwargs):
        return self._db.search_tags(*args, **kwargs)

    def set_scan_concurrency_limit(self, *args, **kwargs):
        return self._db.set_scan_concurrency_limit(*args, **kwargs)

    def subnet_exists(self, *args, **kwargs):
        return self._db.subnet_exists(*args, **kwargs)

    def update_address(self, *args, **kwargs):
        return self._db.update_address(*args, **kwargs)

    def update_dhcp_pool(self, *args, **kwargs):
        return self._db.update_dhcp_pool(*args, **kwargs)

    def update_scan_job(self, *args, **kwargs):
        return self._db.update_scan_job(*args, **kwargs)

    def update_subnet(self, *args, **kwargs):
        return self._db.update_subnet(*args, **kwargs)

    def upsert_scan_schedule(self, *args, **kwargs):
        return self._db.upsert_scan_schedule(*args, **kwargs)

    def validate_address_in_subnet(self, *args, **kwargs):
        return self._db.validate_address_in_subnet(*args, **kwargs)
