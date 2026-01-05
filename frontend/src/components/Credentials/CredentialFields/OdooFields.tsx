import { Control } from "react-hook-form"
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

interface OdooFieldsProps {
  control: Control<any>
}

export function OdooFields({ control }: OdooFieldsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Left Column: Name and Notes */}
      <div className="space-y-4">
        <FormField
          control={control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Name <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <Input placeholder="My Odoo Credential" type="text" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="notes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Notes</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Additional notes..."
                  className="min-h-[200px]"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {/* Right Column: Odoo Connection Details */}
      <div className="space-y-4">
        <FormField
          control={control}
          name="credential_data.url"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                URL <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <Input placeholder="https://your-odoo.com" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="credential_data.database_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Database Name <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <Input placeholder="production" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="credential_data.login"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                Login <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <Input placeholder="admin" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={control}
          name="credential_data.api_token"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                API Token <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <Input type="password" placeholder="••••••••" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
    </div>
  )
}
