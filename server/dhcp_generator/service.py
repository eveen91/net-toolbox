import difflib
import os
import uuid
from . import repository
from .vendor.validation import prepare_artifact


class CheckFailed(Exception):
    def __init__(self, report):
        self.report = report


def prepare(configuration, version_id=None):
    content, report = prepare_artifact(configuration, parser_path=os.environ.get('DHCPD_PARSER_PATH') or None, version_id=version_id)
    if report['syntax_status'] not in ('syntax_checked', 'parser_unavailable'):
        raise CheckFailed(report)
    return content, report


def preview(configuration_id, expected):
    item = repository.get_configuration(configuration_id)
    repository.require_revision(item, expected)
    content, report = prepare(item['configuration'])
    return {'revision': expected, 'content': content.decode('ascii'), 'report': report}


def publish(configuration_id, expected, description, actor):
    item = repository.get_configuration(configuration_id)
    repository.require_revision(item, expected)
    identifier = str(uuid.uuid4())
    content, report = prepare(item['configuration'], identifier)
    return repository.publish(configuration_id, expected, identifier, content, report, description, actor)


def compare(configuration_id, before_id, after_id):
    before, old = repository.artifact(configuration_id, before_id)
    after, new = repository.artifact(configuration_id, after_id)
    def diff(a, b):
        return ''.join(difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                           fromfile=f'version-{before["number"]}', tofile=f'version-{after["number"]}'))
    return {'before': before['number'], 'after': after['number'],
            'text': diff(old.decode('ascii'), new.decode('ascii')),
            'configurationText': diff(repository.dump(before['configuration'])+'\n', repository.dump(after['configuration'])+'\n')}
