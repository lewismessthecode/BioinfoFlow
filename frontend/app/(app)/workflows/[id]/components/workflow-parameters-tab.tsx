"use client"

import { useTranslations } from "next-intl"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { WorkflowSchema } from "@/lib/types"

interface WorkflowParametersTabProps {
  schema: WorkflowSchema | null
}

export function WorkflowParametersTab({ schema }: WorkflowParametersTabProps) {
  const tWorkflows = useTranslations("workflows")

  if (!schema) {
    return (
      <div className="border border-border rounded-lg p-6">
        <div className="text-center text-muted-foreground py-8">
          <p className="text-sm">{tWorkflows("detail.parameters.noInfoTitle")}</p>
          <p className="text-xs mt-1">
            {tWorkflows("detail.parameters.noInfoDescription")}
          </p>
        </div>
      </div>
    )
  }

  const inputs = schema.inputs || []
  const outputs = schema.outputs || []

  return (
    <div className="space-y-6">
      {/* Inputs Section */}
      <div className="border border-border rounded-lg overflow-hidden">
        <div className="bg-secondary/30 px-4 py-3 border-b border-border">
          <h3 className="text-sm font-medium text-foreground">
            {tWorkflows("detail.overview.inputs")}
            <Badge variant="secondary" className="ml-2">
              {inputs.length}
            </Badge>
          </h3>
        </div>
        {inputs.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[200px]">{tWorkflows("detail.parameters.columns.name")}</TableHead>
                <TableHead className="w-[150px]">{tWorkflows("detail.parameters.columns.type")}</TableHead>
                <TableHead className="w-[100px]">{tWorkflows("detail.parameters.columns.required")}</TableHead>
                <TableHead className="w-[200px]">{tWorkflows("detail.parameters.columns.default")}</TableHead>
                <TableHead>{tWorkflows("detail.parameters.columns.description")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {inputs.map((input, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-mono text-sm">{input.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="font-mono text-xs">
                      {input.type}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {input.is_internal ? (
                      <Badge variant="outline" className="text-xs">
                        {tWorkflows("detail.parameters.managed")}
                      </Badge>
                    ) : input.optional ? (
                      <Badge variant="secondary" className="text-xs">
                        {tWorkflows("detail.parameters.optional")}
                      </Badge>
                    ) : (
                      <Badge variant="default" className="text-xs">
                        {tWorkflows("detail.parameters.required")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {input.default || "—"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {input.source_hint ? (
                      tWorkflows(`detail.parameters.fileSource.${input.source_hint}`)
                    ) : (
                      input.description || "—"
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="p-6 text-center text-muted-foreground text-sm">
            {tWorkflows("detail.parameters.noInputs")}
          </div>
        )}
      </div>

      {/* Outputs Section */}
      <div className="border border-border rounded-lg overflow-hidden">
        <div className="bg-secondary/30 px-4 py-3 border-b border-border">
          <h3 className="text-sm font-medium text-foreground">
            {tWorkflows("detail.overview.outputs")}
            <Badge variant="secondary" className="ml-2">
              {outputs.length}
            </Badge>
          </h3>
        </div>
        {outputs.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[200px]">{tWorkflows("detail.parameters.columns.name")}</TableHead>
                <TableHead className="w-[150px]">{tWorkflows("detail.parameters.columns.type")}</TableHead>
                <TableHead className="w-[100px]">{tWorkflows("detail.parameters.columns.optional")}</TableHead>
                <TableHead>{tWorkflows("detail.parameters.columns.description")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {outputs.map((output, idx) => (
                <TableRow key={idx}>
                  <TableCell className="font-mono text-sm">{output.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="font-mono text-xs">
                      {output.type}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {output.value_kind === "file" || output.value_kind === "file_list" ? (
                      <Badge variant="outline" className="text-xs">
                        {tWorkflows("detail.parameters.artifact")}
                      </Badge>
                    ) : output.optional ? (
                      <Badge variant="secondary" className="text-xs">
                        {tWorkflows("detail.parameters.optional")}
                      </Badge>
                    ) : (
                      <Badge variant="default" className="text-xs">
                        {tWorkflows("detail.parameters.required")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {output.description || "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="p-6 text-center text-muted-foreground text-sm">
            {tWorkflows("detail.parameters.noOutputs")}
          </div>
        )}
      </div>
    </div>
  )
}
