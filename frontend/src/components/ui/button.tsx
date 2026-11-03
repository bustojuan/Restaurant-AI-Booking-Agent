import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  icon?: boolean
}
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', icon = false, type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn('button', `button-${variant}`, icon && 'icon-button', className)}
      {...props}
    />
  ),
)
Button.displayName = 'Button'
