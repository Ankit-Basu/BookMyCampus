import { BookmarkSimple } from '@phosphor-icons/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { api, errorMessage } from '../lib/api'

/** Keep a room in your saved list. Sits inside card links, so it must not trigger them. */
export default function SaveButton({ id, saved, labelled }: { id: number; saved: boolean; labelled?: boolean }) {
  const qc = useQueryClient()
  const [on, setOn] = useState(saved)
  const toggle = useMutation({
    mutationFn: (next: boolean) => (next ? api.post(`/resources/${id}/saved`) : api.delete(`/resources/${id}/saved`)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['resources'] })
      qc.invalidateQueries({ queryKey: ['resource', String(id)] })
    },
    onError: (e, next) => {
      setOn(!next)
      toast.error(errorMessage(e))
    },
  })
  const label = on ? 'Remove from saved' : 'Save this room'
  return (
    <button
      type="button"
      className={labelled ? 'key key-ghost key-sm' : `save-btn ${on ? 'on' : ''}`}
      aria-label={label}
      aria-pressed={on}
      title={label}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        setOn(!on)
        toggle.mutate(!on)
      }}
    >
      <BookmarkSimple size={labelled ? 15 : 17} weight={on ? 'fill' : 'bold'} />
      {labelled && (on ? 'Saved' : 'Save')}
    </button>
  )
}
