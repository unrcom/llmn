exports.up = (pgm) => {
  pgm.addColumn({ schema: 'llmn', name: 'ft_conversations' }, {
    split: { type: 'varchar(10)', notNull: true, default: "'train'" },
  })
}

exports.down = (pgm) => {
  pgm.dropColumn({ schema: 'llmn', name: 'ft_conversations' }, 'split')
}
