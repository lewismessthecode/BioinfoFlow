"use client"

import {
  CheckSquare,
  Plus,
  Search,
  RefreshCcw,
  Trash2,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { ViewToggle } from "@/components/ui/view-toggle"
import { formatSize } from "@/lib/format-utils"
import { ImagesGridSkeleton, ImagesTableSkeleton } from "./components/images-skeleton"
import { ImageUploadDialog } from "./components/image-upload-dialog"
import { ImageCardsGrid, ImageTable } from "./components/image-views"
import {
  ImageDetailsSheet,
  OnboardingImagesEmptyState,
  UnavailableImagesEmptyState,
  formatSyncLabel,
} from "./components/image-details"
import { useImagesPage } from "./use-images-page"

export default function ImagesPage() {
  const {
    tImages,
    tCommon,
    images: filteredImages,
    view,
    setView,
    search,
    setSearch,
    uploadOpen,
    setUploadOpen,
    importMethod,
    setImportMethod,
    imageName,
    setImageName,
    selectedRegistry,
    setSelectedRegistry,
    imageRegistries,
    isLoading,
    isSubmitting,
    tarballFile,
    dockerStatus,
    imagesStale,
    lastSyncedAt,
    detailsImage,
    setDetailsImage,
    recommendedOpen,
    setRecommendedOpen,
    recommendedImages,
    isDockerUnavailable,
    hasImages,
    isEmpty,
    selectionMode,
    selectedImageIds,
    selectedImages,
    selectedImagesSize,
    isBatchDeleting,
    hasSelectableImages,
    handleStartSelection,
    handleCancelSelection,
    handleToggleSelection,
    handleBatchDeleteLocal,
    openRegistryDialog,
    openTarballDialog,
    handleRefresh,
    handlePullImage,
    handlePull,
    handleViewDetails,
    handleCopyName,
    handleCopyPullCommand,
    handleDeleteLocal,
    canDeleteImages,
    handleTarballFileChange,
  } = useImagesPage()

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-5">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-foreground">{tImages("title")}</h1>
            <Badge variant="secondary" className="text-xs">{tImages("shared")}</Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            {tImages("subtitle")}
          </p>
        </div>

        {dockerStatus === "unavailable" && (hasImages || imagesStale) && (
          <div className="mb-5 rounded-lg border border-warning/24 bg-warning/7 px-4 py-3 text-sm text-warning-foreground/80">
            <div className="space-y-1">
              <p>{tImages("errors.dockerUnavailableBanner")}</p>
              {lastSyncedAt && (
                <p className="text-xs text-warning-foreground/70">
                  {tImages("meta.lastSynced", { value: formatSyncLabel(lastSyncedAt) })}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Actions Bar */}
        {!isEmpty || !isDockerUnavailable ? (
          <div className="flex items-center justify-between gap-2 sm:gap-4 mb-5">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="image-search"
                placeholder={`${tCommon("search")}...`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
              <Label htmlFor="image-search" className="sr-only">
                {tCommon("search")} {tImages("title")}
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                className="border-border/80 bg-card text-foreground shadow-none hover:bg-accent/70 hover:text-foreground dark:border-border/80 dark:bg-card dark:hover:bg-accent"
                onClick={() => openRegistryDialog()}
                disabled={isDockerUnavailable}
              >
                <Plus className="h-4 w-4 mr-2" />
                {tImages("upload")}
              </Button>

              <Button variant="outline" onClick={handleRefresh}>
                <RefreshCcw className="mr-2 h-4 w-4" />
                {tImages("actions.refresh")}
              </Button>

              {canDeleteImages && hasSelectableImages && view === "cards" ? (
                <Button
                  variant="outline"
                  onClick={selectionMode ? handleCancelSelection : handleStartSelection}
                >
                  {selectionMode ? (
                    <X className="mr-2 h-4 w-4" />
                  ) : (
                    <CheckSquare className="mr-2 h-4 w-4" />
                  )}
                  {selectionMode ? tImages("actions.cancelSelection") : tImages("actions.select")}
                </Button>
              ) : null}

              <ImageUploadDialog
                open={uploadOpen}
                onOpenChange={setUploadOpen}
                importMethod={importMethod}
                onImportMethodChange={setImportMethod}
                imageName={imageName}
                onImageNameChange={setImageName}
                tarballFile={tarballFile}
                onTarballFileChange={handleTarballFileChange}
                registries={imageRegistries}
                selectedRegistry={selectedRegistry}
                onSelectedRegistryChange={setSelectedRegistry}
                isSubmitting={isSubmitting}
                onPull={handlePullImage}
              />

              <ViewToggle view={view} onViewChange={setView} listLabel={tCommon("viewModes.list")} cardsLabel={tCommon("viewModes.cards")} />
            </div>
          </div>
        ) : (
          <ImageUploadDialog
            open={uploadOpen}
            onOpenChange={setUploadOpen}
            importMethod={importMethod}
            onImportMethodChange={setImportMethod}
            imageName={imageName}
            onImageNameChange={setImageName}
            tarballFile={tarballFile}
            onTarballFileChange={handleTarballFileChange}
            registries={imageRegistries}
            selectedRegistry={selectedRegistry}
            onSelectedRegistryChange={setSelectedRegistry}
            isSubmitting={isSubmitting}
            onPull={handlePullImage}
          />
        )}

        {selectionMode && (
          <div className="mb-4 flex flex-col gap-3 rounded-xl border border-border/70 bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-0.5">
              <p className="text-sm font-medium text-foreground">
                {tImages("selection.selectedCount", { count: selectedImages.length })}
              </p>
              <p className="text-xs text-muted-foreground">
                {tImages("selection.selectedSize", { size: formatSize(selectedImagesSize) })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleCancelSelection}>
                <X className="mr-1.5 h-3.5 w-3.5" />
                {tImages("actions.cancelSelection")}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={selectedImages.length === 0 || isBatchDeleting}
                onClick={handleBatchDeleteLocal}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                {tImages("actions.deleteSelectedLocal")}
              </Button>
            </div>
          </div>
        )}

        {/* Images Grid/List */}
        {isLoading ? (
          view === "cards" ? <ImagesGridSkeleton /> : <ImagesTableSkeleton />
        ) : isEmpty && isDockerUnavailable ? (
          <UnavailableImagesEmptyState
            tImages={tImages}
            onRefresh={handleRefresh}
          />
        ) : isEmpty ? (
          <OnboardingImagesEmptyState
            tImages={tImages}
            recommendedOpen={recommendedOpen}
            recommendedImages={recommendedImages}
            onOpenRecommendations={() => setRecommendedOpen((prev) => !prev)}
            onPull={() => openRegistryDialog()}
            onTarball={() => openTarballDialog()}
            onChooseRecommended={(value) => openRegistryDialog(value)}
          />
        ) : view === "cards" ? (
          <ImageCardsGrid
            images={filteredImages}
            tImages={tImages}
            tCommon={tCommon}
            onPull={handlePull}
            onViewDetails={handleViewDetails}
            onCopyName={handleCopyName}
            onCopyPullCommand={handleCopyPullCommand}
            onDeleteLocal={canDeleteImages ? handleDeleteLocal : undefined}
            selectionMode={selectionMode}
            selectedImageIds={selectedImageIds}
            onToggleSelection={handleToggleSelection}
          />
        ) : (
          <ImageTable
            images={filteredImages}
            tImages={tImages}
            tCommon={tCommon}
            onPull={handlePull}
            onViewDetails={handleViewDetails}
            onCopyName={handleCopyName}
            onCopyPullCommand={handleCopyPullCommand}
            onDeleteLocal={canDeleteImages ? handleDeleteLocal : undefined}
          />
        )}

        <ImageDetailsSheet
          image={detailsImage}
          tImages={tImages}
          onPull={handlePull}
          onCopyName={handleCopyName}
          onCopyPullCommand={handleCopyPullCommand}
          onDeleteLocal={canDeleteImages ? handleDeleteLocal : undefined}
          onOpenChange={(open) => {
            if (!open) {
              setDetailsImage(null)
            }
          }}
        />
      </div>
    </div>
  )
}
