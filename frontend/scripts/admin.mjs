import { spawn } from 'node:child_process'
import electron from 'electron'
const env = { ...process.env, BARIA_ADMIN_ONLY: '1' }
delete env.ELECTRON_RUN_AS_NODE
const dev = process.argv[2] === 'dev'
const child = spawn(
  dev ? process.execPath : electron,
  dev ? ['node_modules/electron-vite/bin/electron-vite.js', 'dev'] : ['.', '--admin'],
  { cwd: process.cwd(), env, stdio: 'inherit', windowsHide: true },
)
child.on('exit', (code) => process.exit(code ?? 1))
child.on('error', () => {
  process.stderr.write('No se pudo iniciar AI Control Center.\n')
  process.exit(1)
})
