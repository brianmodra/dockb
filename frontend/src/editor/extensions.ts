import { Node, mergeAttributes } from '@tiptap/core'

export const Chapter = Node.create({
  name: 'chapter',
  topNode: true,
  content: 'paragraph*',

  addAttributes() {
    return {
      id: { default: null },
      title: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-chapter]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-chapter': '' }), 0]
  },
})

export const Paragraph = Node.create({
  name: 'paragraph',
  content: 'sentence*',

  addAttributes() {
    return {
      id: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-paragraph]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, { 'data-paragraph': '' }),
      0,
    ]
  },
})

export const Sentence = Node.create({
  name: 'sentence',
  content: 'text*',

  addAttributes() {
    return {
      id: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'span[data-sentence]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(HTMLAttributes, { 'data-sentence': '' }),
      0,
    ]
  },
})
