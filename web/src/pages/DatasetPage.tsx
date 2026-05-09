import { useEffect, useState } from 'react'
import { apiClient } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Trash2, Plus, Pencil, Check, X } from 'lucide-react'

interface Project { id: number; display_name: string }
interface Dataset { id: number; project_id: number; name: string; display_name: string; description: string | null; created_at: string }
interface Document { id: string; content: string }

export default function DatasetPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])

  // データセット作成
  const [creatingDataset, setCreatingDataset] = useState(false)

  // ドキュメント追加
  const [newDocContent, setNewDocContent] = useState('')
  const [showAddDoc, setShowAddDoc] = useState(false)
  const [savingDoc, setSavingDoc] = useState(false)

  // ドキュメント編集
  const [editingDocId, setEditingDocId] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    apiClient.get('/projects').then(res => setProjects(res.data))
  }, [])

  useEffect(() => {
    if (!selectedProjectId) {
      setDataset(null)
      setDocuments([])
      return
    }
    setLoading(true)
    setError(null)
    apiClient.get(`/datasets?project_id=${selectedProjectId}`)
      .then(res => {
        const list: Dataset[] = res.data
        if (list.length > 0) {
          setDataset(list[0])
          return apiClient.get(`/datasets/${list[0].id}/documents`)
        } else {
          setDataset(null)
          setDocuments([])
          return null
        }
      })
      .then(res => {
        if (res) setDocuments(res.data)
      })
      .catch(() => setError('データの読み込みに失敗しました'))
      .finally(() => setLoading(false))
  }, [selectedProjectId])

  async function createDataset() {
    if (!selectedProjectId) return
    const project = projects.find(p => p.id === selectedProjectId)
    if (!project) return
    setCreatingDataset(true)
    setError(null)
    try {
      const res = await apiClient.post('/datasets', {
        project_id: selectedProjectId,
        display_name: project.display_name,
      })
      setDataset(res.data)
      setDocuments([])
    } catch (e: any) {
      setError(e.response?.data?.detail || 'データセットの作成に失敗しました')
    } finally {
      setCreatingDataset(false)
    }
  }

  async function deleteDataset() {
    if (!dataset || !confirm(`データセット「${dataset.display_name}」を削除しますか？\nドキュメントもすべて削除されます。`)) return
    setError(null)
    try {
      await apiClient.delete(`/datasets/${dataset.id}`)
      setDataset(null)
      setDocuments([])
    } catch (e: any) {
      setError(e.response?.data?.detail || 'データセットの削除に失敗しました')
    }
  }

  async function addDocument() {
    if (!newDocContent.trim() || !dataset) return
    setError(null)
    setSavingDoc(true)
    try {
      await apiClient.post(`/datasets/${dataset.id}/documents`, { content: newDocContent })
      setNewDocContent('')
      setShowAddDoc(false)
      const res = await apiClient.get(`/datasets/${dataset.id}/documents`)
      setDocuments(res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'エラーが発生しました')
    } finally {
      setSavingDoc(false)
    }
  }

  async function updateDocument(docId: string) {
    if (!dataset) return
    setError(null)
    try {
      await apiClient.put(`/datasets/${dataset.id}/documents/${docId}`, { content: editingContent })
      setEditingDocId(null)
      const res = await apiClient.get(`/datasets/${dataset.id}/documents`)
      setDocuments(res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'エラーが発生しました')
    }
  }

  async function deleteDocument(docId: string) {
    if (!dataset || !confirm('削除しますか？')) return
    await apiClient.delete(`/datasets/${dataset.id}/documents/${docId}`)
    setDocuments(d => d.filter(x => x.id !== docId))
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">

      {/* プロジェクト選択 */}
      <div>
        <Label className="text-xs text-gray-500 mb-1 block">プロジェクト</Label>
        <select
          className="w-full border rounded px-3 py-2 text-sm bg-white"
          value={selectedProjectId ?? ''}
          onChange={e => setSelectedProjectId(Number(e.target.value) || null)}
        >
          <option value="">-- 選択してください --</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.display_name}</option>)}
        </select>
      </div>

      {/* ドキュメントエリア */}
      {selectedProjectId && (
        <>
          {loading ? (
            <div className="text-sm text-gray-400">読み込み中...</div>
          ) : !dataset ? (
            <div className="border rounded p-4 bg-gray-50 space-y-3">
              <p className="text-sm text-gray-500">このプロジェクトにはデータセットがありません。</p>
              <Button size="sm" onClick={createDataset} disabled={creatingDataset}>
                <Plus className="h-3 w-3 mr-1" />{creatingDataset ? '作成中...' : 'データセットを作成'}
              </Button>
              {error && <div className="text-red-500 text-sm">{error}</div>}
            </div>
          ) : (
            <div className="space-y-4">

              {/* ヘッダー */}
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-gray-700">{dataset.display_name}</span>
                  <span className="ml-2 text-xs text-gray-400">{documents.length} 件</span>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => { setShowAddDoc(v => !v); setError(null) }}>
                    <Plus className="h-3 w-3 mr-1" /> 追加
                  </Button>
                  <Button size="sm" variant="outline" onClick={deleteDataset} className="text-red-500 hover:text-red-700 hover:border-red-300">
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {error && <div className="text-red-500 text-sm">{error}</div>}

              {/* ドキュメント追加フォーム */}
              {showAddDoc && (
                <div className="border rounded p-3 bg-gray-50 space-y-2">
                  <Textarea
                    rows={4}
                    placeholder='{"title": "...", "content": "..."}'
                    value={newDocContent}
                    onChange={e => setNewDocContent(e.target.value)}
                    className="text-sm font-mono"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={addDocument} disabled={savingDoc}>
                      {savingDoc ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />登録中...</> : '登録'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setShowAddDoc(false); setNewDocContent('') }}>キャンセル</Button>
                  </div>
                </div>
              )}

              {/* ドキュメント一覧 */}
              <div className="space-y-2">
                {documents.length === 0 ? (
                  <div className="text-sm text-gray-400 text-center py-8">ドキュメントがありません</div>
                ) : (
                  documents.map(doc => (
                    <div key={doc.id} className="border rounded p-3 bg-white">
                      {editingDocId === doc.id ? (
                        <div className="space-y-2">
                          <Textarea
                            rows={4}
                            value={editingContent}
                            onChange={e => setEditingContent(e.target.value)}
                            className="text-sm font-mono"
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={() => updateDocument(doc.id)}><Check className="h-3 w-3 mr-1" />保存</Button>
                            <Button size="sm" variant="outline" onClick={() => setEditingDocId(null)}><X className="h-3 w-3 mr-1" />キャンセル</Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <pre className="text-sm flex-1 whitespace-pre-wrap break-all font-mono">{doc.content}</pre>
                          <div className="flex gap-1 shrink-0">
                            <button onClick={() => { setEditingDocId(doc.id); setEditingContent(doc.content) }} className="text-gray-400 hover:text-blue-500">
                              <Pencil className="h-3 w-3" />
                            </button>
                            <button onClick={() => deleteDocument(doc.id)} className="text-gray-400 hover:text-red-500">
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

            </div>
          )}
        </>
      )}

    </div>
  )
}
