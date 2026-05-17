import { useState, useRef } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { apiClient, clearTokens, getIsAdmin } from '@/api/client'
import {
  MessageSquare, FolderOpen, Cpu, Wrench,
  ChevronDown, ChevronRight, LogOut, Database, Menu, X, BookOpen,
  Download, Upload, Loader2,
} from 'lucide-react'

const adminItems = [
  { to: '/admin/projects',  label: 'プロジェクト', icon: FolderOpen },
  { to: '/admin/models',    label: 'モデル',       icon: Cpu },
  { to: '/admin/ft-data',   label: 'FTデータ管理', icon: BookOpen },
  { to: '/admin/jobs',      label: '訓練ジョブ',   icon: Wrench },
]

export default function Layout() {
  const navigate = useNavigate()
  const isAdmin = getIsAdmin()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [adminOpen, setAdminOpen] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [backupMsg, setBackupMsg] = useState<string | null>(null)
  const importAllRef = useRef<HTMLInputElement>(null)

  async function onLogout() {
    try {
      const refreshToken = localStorage.getItem('llmn_refresh_token')
      if (refreshToken) await apiClient.post('/auth/logout', { refresh_token: refreshToken })
    } catch {}
    clearTokens()
    navigate('/login')
  }

  async function exportAll() {
    setExporting(true)
    setBackupMsg(null)
    try {
      const res = await apiClient.get('/datasets/export/all', { responseType: 'blob' })
      const cd = res.headers['content-disposition'] || ''
      const match = cd.match(/filename="(.+)"/)
      const filename = match ? match[1] : 'llamune_backup.md'
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/markdown' }))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      setBackupMsg('エクスポート完了')
    } catch {
      setBackupMsg('エクスポート失敗')
    } finally {
      setExporting(false)
      setTimeout(() => setBackupMsg(null), 3000)
    }
  }

  async function handleImportAll(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.[0]) return
    const file = e.target.files[0]
    e.target.value = ''
    if (!confirm('全体バックアップをインポートします。既存のドキュメントは上書きされます。よろしいですか？')) return
    setImporting(true)
    setBackupMsg(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post('/datasets/import/all', form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      const msg = `インポート完了：${res.data.imported}件、スキップ${res.data.skipped}件`
      setBackupMsg('✓ ' + msg)
    } catch (e: any) {
      setBackupMsg('⚠ ' + (e.response?.data?.detail || 'リストアに失敗しました'))
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className={`border-r bg-white flex flex-col shrink-0 transition-all duration-200 ${sidebarOpen ? 'w-48' : 'w-12'}`}>
        <div className="flex items-center justify-between p-3 border-b h-14">
          {sidebarOpen && <h1 className="font-bold text-blue-600">llamune</h1>}
          <button onClick={() => setSidebarOpen(o => !o)} className="p-1 rounded hover:bg-gray-100 text-gray-500 ml-auto">
            {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>

        <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
          <NavLink
            to="/chat"
            title={!sidebarOpen ? 'チャット' : undefined}
            className={({ isActive }) =>
              `flex items-center gap-2 py-2 rounded text-sm transition-colors ${sidebarOpen ? 'px-3' : 'justify-center px-2'} ${isActive ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-600 hover:bg-gray-100'}`
            }
          >
            <MessageSquare className="h-4 w-4 shrink-0" />
            {sidebarOpen && 'チャット'}
          </NavLink>

          <NavLink
            to="/dataset"
            title={!sidebarOpen ? 'データセット' : undefined}
            className={({ isActive }) =>
              `flex items-center gap-2 py-2 rounded text-sm transition-colors ${sidebarOpen ? 'px-3' : 'justify-center px-2'} ${isActive ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-600 hover:bg-gray-100'}`
            }
          >
            <Database className="h-4 w-4 shrink-0" />
            {sidebarOpen && 'データセット'}
          </NavLink>

          {isAdmin && (
            <div>
              {sidebarOpen && (
                <button
                  onClick={() => setAdminOpen(o => !o)}
                  className="flex items-center gap-2 px-3 py-2 rounded text-sm text-gray-500 hover:bg-gray-100 w-full mt-2"
                >
                  {adminOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  管理
                </button>
              )}
              {(adminOpen || !sidebarOpen) && (
                <div className={sidebarOpen ? 'ml-2 space-y-1' : 'space-y-1 mt-1'}>
                  {adminItems.map(({ to, label, icon: Icon }) => (
                    <NavLink
                      key={to}
                      to={to}
                      title={!sidebarOpen ? label : undefined}
                      className={({ isActive }) =>
                        `flex items-center gap-2 py-2 rounded text-sm transition-colors ${sidebarOpen ? 'px-3' : 'justify-center px-2'} ${isActive ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-600 hover:bg-gray-100'}`
                      }
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {sidebarOpen && label}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          )}
        </nav>

        {/* バックアップ・リストア */}
        <div className="p-2 border-t space-y-1">
          {sidebarOpen && backupMsg && (
            <div className={`text-xs px-2 pb-1 flex items-start justify-between gap-1 ${backupMsg.startsWith('⚠') ? 'text-red-500' : 'text-green-600'}`}>
              <span>{backupMsg}</span>
              <button onClick={() => setBackupMsg(null)} className="shrink-0 mt-0.5"><X className="h-3 w-3" /></button>
            </div>
          )}
          <button
            onClick={exportAll}
            disabled={exporting}
            title={!sidebarOpen ? '全体エクスポート' : undefined}
            className={`flex items-center gap-2 py-2 rounded text-sm text-gray-600 hover:bg-gray-100 w-full ${sidebarOpen ? 'px-3' : 'justify-center px-2'}`}
          >
            {exporting ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : <Download className="h-4 w-4 shrink-0" />}
            {sidebarOpen && 'バックアップ'}
          </button>
          <button
            onClick={() => importAllRef.current?.click()}
            disabled={importing}
            title={!sidebarOpen ? '全体インポート' : undefined}
            className={`flex items-center gap-2 py-2 rounded text-sm text-gray-600 hover:bg-gray-100 w-full ${sidebarOpen ? 'px-3' : 'justify-center px-2'}`}
          >
            {importing ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : <Upload className="h-4 w-4 shrink-0" />}
            {sidebarOpen && 'リストア'}
          </button>
          <input ref={importAllRef} type="file" accept=".md" className="hidden" onChange={handleImportAll} />

          <button
            onClick={onLogout}
            title={!sidebarOpen ? 'ログアウト' : undefined}
            className={`flex items-center gap-2 py-2 rounded text-sm text-gray-600 hover:bg-gray-100 w-full ${sidebarOpen ? 'px-3' : 'justify-center px-2'}`}
          >
            <LogOut className="h-4 w-4 shrink-0" />
            {sidebarOpen && 'ログアウト'}
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
