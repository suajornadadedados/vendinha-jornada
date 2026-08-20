module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [2, 'always',
      ['feat', 'fix', 'test', 'docs', 'spec', 'adr', 'eval', 'ci', 'chore', 'refactor']],
    'scope-empty': [2, 'never'], // escopo obrigatório: s-XX ou área (deploy, harness)
  },
};
