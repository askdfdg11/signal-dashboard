import os
from common import report_status

event = os.getenv('GITHUB_EVENT_NAME', 'local')
if event == 'schedule':
    state, message = 'scheduled_run_observed', 'GitHub 예약 실행 이력 확인 · 예정 시각 대비 지연 가능'
elif event == 'workflow_dispatch':
    state, message = 'manual_run_observed', 'GitHub 수동 실행 확인 · 정시 예약 발동은 아직 확인 전'
else:
    state, message = 'unverified', '정시 예약 발동 확인 전'
report_status('execution', state, message, event=event,
    run_url=f"https://github.com/{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}")
