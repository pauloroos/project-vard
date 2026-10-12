; Remove o atalho de inicio com o Windows criado pelo painel de configuracoes.
!macro NSIS_HOOK_PREUNINSTALL
  Delete "$SMSTARTUP\Vard.lnk"
!macroend
