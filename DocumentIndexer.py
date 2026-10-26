import csv
import os
from contextlib import ExitStack
from pathlib import Path


# CHANGE THESE TWO PATHS
ROOT_FOLDER = Path(r"C:\Data\Documents")
OUTPUT_FOLDER = Path(r"C:\Data\DocumentIndex")

# Expected structure:
# ROOT_FOLDER / useless inner folder / PersonalIdentifier / document.pdf

FIELDS = [
    "PersonalIdentifier",
    "DocumentName",
    "HTMLExists",
    "MTDDExists",
    "PDFExists",
    "MTDDMissingPDF",
    "PDFPath",
    "MTDDPath",
    "HTMLPath",
]

EXTENSIONS = {
    ".html": "html",
    ".htm": "html",
    ".mtdd": "mtdd",
    ".pdf": "pdf",
}


def run_index(root, output):
    root = Path(root).resolve()
    output = Path(output).resolve()

    if not root.is_dir():
        raise ValueError(f"Root folder not found or inaccessible: {root}")

    if output == root or root in output.parents:
        raise ValueError("OUTPUT_FOLDER must be outside ROOT_FOLDER.")

    with os.scandir(root) as entries:
        inner_folders = [
            Path(entry.path)
            for entry in entries
            if entry.is_dir(follow_symlinks=False)
        ]

    if len(inner_folders) != 1:
        raise ValueError(
            "Expected exactly 1 inner folder directly under ROOT_FOLDER. "
            f"Found {len(inner_folders)}."
        )

    output.mkdir(parents=True, exist_ok=True)

    counts = {
        "folders": 0,
        "documents": 0,
        "pdfs": 0,
        "missing": 0,
        "errors": 0,
    }

    with ExitStack() as stack:
        writers = {}

        for name in ("document_audit", "pdf_index", "mtdd_missing_pdf"):
            handle = stack.enter_context(
                (output / f"{name}.csv").open(
                    "w",
                    newline="",
                    encoding="utf-8",
                )
            )

            writers[name] = csv.DictWriter(handle, fieldnames=FIELDS)
            writers[name].writeheader()

        error_handle = stack.enter_context(
            (output / "scan_errors.csv").open(
                "w",
                newline="",
                encoding="utf-8",
            )
        )

        error_writer = csv.writer(error_handle)
        error_writer.writerow(["Path", "Error"])

        def log_error(path, message):
            counts["errors"] += 1
            error_writer.writerow([str(path), str(message)])

        with os.scandir(inner_folders[0]) as people:
            for person in people:
                try:
                    if not person.is_dir(follow_symlinks=False):
                        log_error(
                            person.path,
                            "Expected a personal identifier folder.",
                        )
                        continue

                    counts["folders"] += 1
                    documents = {}

                    with os.scandir(person.path) as files:
                        for file in files:
                            if not file.is_file(follow_symlinks=False):
                                log_error(
                                    file.path,
                                    "Nested folder or link skipped.",
                                )
                                continue

                            path = Path(file.path)
                            kind = EXTENSIONS.get(path.suffix.lower())

                            if kind is None:
                                continue

                            # Match versions by name, ignoring capitalization.
                            # Only remove the final extension.
                            key = path.stem.casefold()

                            document = documents.setdefault(
                                key,
                                {
                                    "name": path.stem,
                                    "files": {},
                                },
                            )

                            if kind in document["files"]:
                                log_error(
                                    path,
                                    f"Duplicate {kind} version; using "
                                    f"{document['files'][kind]}",
                                )
                                continue

                            document["files"][kind] = str(path)

                            # Prefer the PDF's capitalization for the name.
                            if kind == "pdf":
                                document["name"] = path.stem

                except OSError as exc:
                    # Skip incomplete folder results to avoid false
                    # missing-PDF flags.
                    log_error(person.path, exc)
                    continue

                for key in sorted(documents):
                    document = documents[key]
                    versions = document["files"]

                    missing_pdf = (
                        "mtdd" in versions
                        and "pdf" not in versions
                    )

                    row = {
                        "PersonalIdentifier": person.name,
                        "DocumentName": document["name"],
                        "HTMLExists": int("html" in versions),
                        "MTDDExists": int("mtdd" in versions),
                        "PDFExists": int("pdf" in versions),
                        "MTDDMissingPDF": int(missing_pdf),
                        "PDFPath": versions.get("pdf", ""),
                        "MTDDPath": versions.get("mtdd", ""),
                        "HTMLPath": versions.get("html", ""),
                    }

                    writers["document_audit"].writerow(row)
                    counts["documents"] += 1

                    if "pdf" in versions:
                        writers["pdf_index"].writerow(row)
                        counts["pdfs"] += 1

                    if missing_pdf:
                        writers["mtdd_missing_pdf"].writerow(row)
                        counts["missing"] += 1

                progress = (
                    f"Folders: {counts['folders']:,} | "
                    f"Documents: {counts['documents']:,} | "
                    f"PDFs: {counts['pdfs']:,} | "
                    f"MTDD missing PDF: {counts['missing']:,} | "
                    f"Errors: {counts['errors']:,}"
                )

                print(f"\r{progress}", end="", flush=True)

    print()

    if counts["errors"]:
        print("Finished with issues. Review scan_errors.csv.")
    else:
        print("Finished.")

    print(f"Output: {output}")
    return counts


if __name__ == "__main__":
    try:
        result = run_index(ROOT_FOLDER, OUTPUT_FOLDER)
        raise SystemExit(1 if result["errors"] else 0)

    except (OSError, ValueError) as exc:
        print(f"\nFAILED: {exc}")
        print("Output may be incomplete or from an earlier run.")
        raise SystemExit(1)

    except KeyboardInterrupt:
        print("\nStopped. Output is partial; rerun to rebuild it.")
        raise SystemExit(130)
