import { useState } from 'react'
import { api } from '../../api/client'
import type { Installation, Repository, Settings } from '../../api/types'
import { Panel } from '../../components/Panel'
import { Toggle } from '../../components/Toggle'
import { ConfirmModal } from '../../components/modals/ConfirmModal'
import './SettingsForm.css'

// repository가 없으면 설치 계정의 공통 설정, 있으면 저장소 설정을 편집한다
export function SettingsForm({
  installation,
  repository,
  csrf,
  onSaved,
}: {
  installation: Installation
  repository?: Repository
  csrf: string
  onSaved: () => Promise<void>
}) {
  const initialSettings = repository?.settings ?? installation.settings
  const [settings, setSettings] = useState<Settings>(initialSettings)
  const [paused, setPaused] = useState(installation.paused)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(
    null,
  )
  const [confirming, setConfirming] = useState(false)
  const canManage = repository
    ? repository.permission === 'admin'
    : installation.can_manage
  const disabled = !canManage || !!repository?.use_common || busy
  const dirty =
    JSON.stringify(settings) !== JSON.stringify(initialSettings) ||
    (!repository && paused !== installation.paused)

  async function save() {
    setBusy(true)
    setMessage(null)
    try {
      const path = repository
        ? `/settings/repositories/${repository.id}`
        : `/settings/installations/${installation.id}`
      await api(
        path,
        {
          method: 'PUT',
          body: JSON.stringify(
            repository ? { use_common: false, settings } : { settings, paused },
          ),
        },
        csrf,
      )
      await onSaved()
      setMessage({ ok: true, text: '✔ 설정을 저장했습니다.' })
    } catch (error) {
      setMessage({ ok: false, text: `✖ ${(error as Error).message}` })
    } finally {
      setBusy(false)
    }
  }

  async function applyCommon(value: boolean) {
    if (!repository) return
    setConfirming(false)
    setBusy(true)
    setMessage(null)
    try {
      await api(
        `/settings/repositories/${repository.id}`,
        { method: 'PUT', body: JSON.stringify({ use_common: value }) },
        csrf,
      )
      await onSaved()
    } catch (error) {
      setMessage({ ok: false, text: `✖ ${(error as Error).message}` })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel
      title={`리뷰 정책 · ${repository ? '저장소 설정' : '공통 설정'}`}
      className="policy"
    >
      <div className="policy-head">
        <div>
          <small>{repository ? '저장소 설정' : '공통 설정'}</small>
          <strong>{repository?.full_name ?? installation.login}</strong>
        </div>
        <span className="tag">
          {repository
            ? '저장소'
            : installation.account_type === 'User'
              ? '개인 계정'
              : '조직'}
        </span>
      </div>
      {!canManage && (
        <p className="readonly-notice">
          🔒 변경은{' '}
          {repository ? '저장소 Admin' : '개인 계정 소유자 또는 조직 Owner'}에게
          요청해 주세요.
        </p>
      )}
      {repository && (
        <Toggle
          label="공통 설정 사용"
          checked={repository.use_common}
          onChange={(value) => (value ? setConfirming(true) : applyCommon(false))}
          disabled={!canManage || busy}
          description={
            repository.use_common
              ? `${installation.login}의 공통 설정과 이후 변경을 따릅니다.`
              : '이 저장소의 설정을 독립적으로 관리합니다.'
          }
        />
      )}
      <Toggle
        label="자동 리뷰"
        checked={settings.automatic}
        onChange={(automatic) => setSettings({ ...settings, automatic })}
        disabled={disabled}
        description="끄면 새 자동 리뷰와 대기 중인 자동 리뷰가 중지됩니다. 진행 중인 리뷰는 완료하며, 수동 리뷰와 재시도는 가능합니다."
      />
      <label className="field">
        <b>
          추가 리뷰 지침 <small className="muted">(선택)</small>
        </b>
        <small>
          비워 두면 기본 기준을 사용합니다. 팀의 규칙이나 중점적으로 확인할
          내용을 적어 주세요.
        </small>
        <span className="textarea-wrap">
          <textarea
            value={settings.instructions}
            maxLength={12000}
            rows={6}
            placeholder="예: 공개 API를 변경할 때 하위 호환성을 확인해 주세요."
            disabled={disabled}
            onChange={(e) =>
              setSettings({ ...settings, instructions: e.target.value })
            }
          />
          <em>
            {settings.instructions.length.toLocaleString()} / 12,000
          </em>
        </span>
      </label>
      <label className="field">
        <b>제외 경로</b>
        <small>분석에서 제외할 glob 패턴을 한 줄에 하나씩 입력해 주세요.</small>
        <textarea
          className="code-editor"
          rows={5}
          value={settings.exclude_patterns.join('\n')}
          placeholder={'**/*.lock\ndist/**'}
          disabled={disabled}
          onChange={(e) =>
            setSettings({
              ...settings,
              exclude_patterns: e.target.value.split('\n'),
            })
          }
        />
      </label>
      {!repository && (
        <div className="danger-zone">
          <Toggle
            label="이 계정의 전체 리뷰 중지"
            checked={paused}
            onChange={setPaused}
            disabled={!canManage || busy}
            description="모든 저장소의 새 자동·수동 리뷰와 재시도를 막고 대기 작업을 취소합니다. 이미 진행 중인 작업은 완료합니다."
          />
        </div>
      )}
      <div className="form-footer">
        <span
          role="status"
          className={message ? (message.ok ? 'accent' : 'danger') : 'warning'}
        >
          {message?.text ?? (dirty && !busy ? '[+] 저장 안 됨' : '')}
        </span>
        <button
          className="button primary"
          disabled={disabled || !dirty}
          onClick={save}
        >
          {busy ? '⠋ 저장 중…' : '설정 저장'}
        </button>
      </div>
      {confirming && (
        <ConfirmModal
          message="저장소의 독립 설정을 버리고 공통 설정을 적용합니다. 계속할까요?"
          confirmLabel="적용"
          onCancel={() => setConfirming(false)}
          onConfirm={() => applyCommon(true)}
        />
      )}
    </Panel>
  )
}
