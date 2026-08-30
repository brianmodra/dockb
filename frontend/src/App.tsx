import { useState } from 'react'
import { DocumentList } from '@/components/DocumentList'
import { ChapterView } from '@/components/ChapterView'
import type { Document } from '@/types'

type ViewState =
  | { screen: 'documents' }
  | { screen: 'chapters'; document: Document }

export default function App() {
  const [view, setView] = useState<ViewState>({ screen: 'documents' })

  return (
    <div className="app">
      {view.screen === 'documents' && (
        <DocumentList
          onSelect={(doc) => setView({ screen: 'chapters', document: doc })}
        />
      )}
      {view.screen === 'chapters' && (
        <ChapterView
          document={view.document}
          onBack={() => setView({ screen: 'documents' })}
        />
      )}
    </div>
  )
}
