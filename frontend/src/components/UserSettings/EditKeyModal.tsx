import { useState, useEffect } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { SshKeysService, type SSHKeyPublic } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { Copy } from "lucide-react"

interface EditKeyModalProps {
  sshKey: SSHKeyPublic
  open: boolean
  onClose: () => void
}

export function EditKeyModal({ sshKey, open, onClose }: EditKeyModalProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [keyName, setKeyName] = useState(sshKey.name)

  // Update form when sshKey changes
  useEffect(() => {
    setKeyName(sshKey.name)
  }, [sshKey])

  const updateMutation = useMutation({
    mutationFn: (name: string) =>
      SshKeysService.updateSshKey({
        id: sshKey.id,
        requestBody: { name }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sshKeys"] })
      showSuccessToast("SSH key updated successfully")
      onClose()
    },
    onError: (error: any) => {
      showErrorToast(error.body?.detail || "Failed to update SSH key")
    },
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!keyName.trim() || keyName === sshKey.name) {
      onClose()
      return
    }

    updateMutation.mutate(keyName.trim())
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    showSuccessToast("Public key copied to clipboard")
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[600px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Edit SSH Key</DialogTitle>
            <DialogDescription>
              Update the name of your SSH key. The key itself cannot be modified.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-key-name">Key Name</Label>
              <Input
                id="edit-key-name"
                placeholder="e.g., GitHub Deploy Key - Docs"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label>Public Key</Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => copyToClipboard(sshKey.public_key)}
                >
                  <Copy className="h-4 w-4 mr-2" />
                  Copy
                </Button>
              </div>
              <Textarea
                value={sshKey.public_key}
                readOnly
                className="font-mono text-xs h-24 bg-muted"
              />
            </div>

            <div className="grid gap-2">
              <Label>Fingerprint</Label>
              <Input
                value={sshKey.fingerprint}
                readOnly
                className="font-mono text-xs bg-muted"
              />
            </div>

            <div className="border-t pt-3">
              <p className="text-xs text-muted-foreground">
                <strong>Security Note:</strong> The private key is encrypted and stored securely.
                It cannot be viewed or exported.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!keyName.trim() || updateMutation.isPending}
            >
              {updateMutation.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
