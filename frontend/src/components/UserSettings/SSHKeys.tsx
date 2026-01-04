import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { SshKeysService, type SSHKeyPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import useCustomToast from "@/hooks/useCustomToast"
import { GenerateKeyModal } from "./GenerateKeyModal"
import { ImportKeyModal } from "./ImportKeyModal"
import { EditKeyModal } from "./EditKeyModal"
import { Copy, Pencil, Trash2 } from "lucide-react"

export function SSHKeys() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [editKey, setEditKey] = useState<SSHKeyPublic | null>(null)
  const [deleteKeyId, setDeleteKeyId] = useState<string | null>(null)

  // Fetch SSH keys
  const { data: keysData, isLoading } = useQuery({
    queryKey: ["sshKeys"],
    queryFn: () => SshKeysService.readSshKeys(),
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => SshKeysService.deleteSshKey({ id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sshKeys"] })
      showSuccessToast("SSH key deleted successfully")
      setDeleteKeyId(null)
    },
    onError: () => {
      showErrorToast("Failed to delete SSH key")
    },
  })

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    showSuccessToast("Public key copied to clipboard")
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    })
  }

  const truncateFingerprint = (fingerprint: string) => {
    if (fingerprint.length > 30) {
      return fingerprint.substring(0, 27) + "..."
    }
    return fingerprint
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>SSH Keys</CardTitle>
          <CardDescription>
            Manage SSH keys for accessing private Git repositories. Keys are encrypted and stored securely.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Button onClick={() => setGenerateModalOpen(true)}>
              Generate Key
            </Button>
            <Button variant="outline" onClick={() => setImportModalOpen(true)}>
              Import Key
            </Button>
          </div>

          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading SSH keys...</div>
          ) : keysData && keysData.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Fingerprint</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keysData.data.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {truncateFingerprint(key.fingerprint)}
                    </TableCell>
                    <TableCell>{formatDate(key.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex gap-2 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => copyToClipboard(key.public_key)}
                          title="Copy public key"
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditKey(key)}
                          title="Edit"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteKeyId(key.id)}
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-sm text-muted-foreground">
              No SSH keys found. Generate or import a key to get started.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Generate Key Modal */}
      <GenerateKeyModal
        open={generateModalOpen}
        onClose={() => setGenerateModalOpen(false)}
      />

      {/* Import Key Modal */}
      <ImportKeyModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
      />

      {/* Edit Key Modal */}
      {editKey && (
        <EditKeyModal
          sshKey={editKey}
          open={!!editKey}
          onClose={() => setEditKey(null)}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteKeyId} onOpenChange={(open) => !open && setDeleteKeyId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete SSH Key</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this SSH key? This action cannot be undone.
              {" "}If this key is used by any knowledge sources, those sources will be marked as disconnected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteKeyId && deleteMutation.mutate(deleteKeyId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
