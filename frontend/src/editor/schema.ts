import { Schema } from '@tiptap/pm/model'

export const chapterSchema = new Schema({
  topNode: 'chapter',
  nodes: {
    chapter: {
      content: 'paragraph*',
      attrs: { id: { default: null }, title: { default: null } },
      parseDOM: [{ tag: 'div[data-chapter]' }],
      toDOM() {
        return ['div', { 'data-chapter': '' }, 0]
      },
    },
    paragraph: {
      content: 'sentence*',
      attrs: { id: { default: null } },
      parseDOM: [{ tag: 'div[data-paragraph]' }],
      toDOM() {
        return ['div', { 'data-paragraph': '' }, 0]
      },
    },
    sentence: {
      content: 'text*',
      attrs: { id: { default: null } },
      parseDOM: [{ tag: 'span[data-sentence]' }],
      toDOM() {
        return ['span', { 'data-sentence': '' }, 0]
      },
    },
    text: {
      inline: true,
    },
  },
})
