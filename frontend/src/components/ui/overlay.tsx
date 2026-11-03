import { en } from '../../i18n/en'
import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { X } from 'lucide-react'
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Button } from './button'
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  title: string
  description?: string
  children: ReactNode
  wide?: boolean
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content className={`modal ${wide ? 'modal-wide' : ''}`}>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
          >
            <div className="modal-heading">
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Close asChild>
                <Button variant="ghost" icon aria-label={en.close}>
                  <X size={19} />
                </Button>
              </Dialog.Close>
            </div>
            <Dialog.Description className={description ? 'modal-description' : 'sr-only'}>
              {description ?? title}
            </Dialog.Description>
            {children}
          </motion.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
export function Pop({
  trigger,
  children,
  className = '',
  open,
  onOpenChange,
  alignOffset = 0,
}: {
  trigger: ReactNode
  children: ReactNode
  className?: string
  open?: boolean
  onOpenChange?: (v: boolean) => void
  alignOffset?: number
}) {
  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          alignOffset={alignOffset}
          sticky="always"
          sideOffset={14}
          collisionPadding={18}
          className={`popover ${className}`}
        >
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.14 }}
          >
            {children}
          </motion.div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
