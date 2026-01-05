import { UseFormReturn } from "react-hook-form"
import { ApiTokenFields } from "@/components/Credentials/CredentialFields"

interface ApiTokenCredentialFormProps {
  form: UseFormReturn<any>
}

export function ApiTokenCredentialForm({ form }: ApiTokenCredentialFormProps) {
  return <ApiTokenFields control={form.control} watch={form.watch} />
}
