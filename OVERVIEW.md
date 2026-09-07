# This is a documentation of the current state of the project, which needs to be maintained at all times

# A short description of the projects intensions, philosophy and style can be found in PROJECT.md

# All architectural/technical decisions and standards can be found and have to be maintained in SPECS.md

-- Example --

# if a feature/attribute is implemented, set marker to "+"
# if all requirements are implemented, set marker to "done"

done: fully implemented specification
    + implemented requirement

todo: partly implemented specification
    + implemented requirement
    - missing/new requirement

-- Project --

done: frontend and backend first layout
    + Frontend input: pdf, png, jpg
    + Frontend pdf scrollable preview with "-" buttons for future page-removing functionality
    + Frontend convert options: png to jpg/pdf, jpg to png/pdf
    + Frontend if pdf then show pdf preview else show convert options
    + Frontend convert / apply changes(pdf) button
    + Frontend download button
    + Backend load input functionality: pdf, png, jpg
    + Backend converting methods
    + Backend remove pdf page functionality

done: view features
    + expand button on the top right of the preview (pdf pages and image) opening a bigger scrollable preview popup
    + the expanded view contains the "-" buttons too, marking pages in either view keeps both in sync

done: input features
    + "+ Add file" button uploads more files of the same kind (a different format is refused)
    + pdf pages of all added files are merged, the button reads "Merge & apply changes"
    + images: several files become the pages of one pdf, the button reads "Merge & convert"
    + move buttons next to the "-" button change the page order, in both previews

done: pdf features
    + a removed page disappears instantly from both previews
    + undo/redo buttons in the pages panel and in the expanded preview bring it back (ctrl/cmd+z, shift+ctrl/cmd+z)
    + undo also steps back over an applied change, restoring the previous document

done: main.py file to start backend and frontend
    + proper shutdown is ensured when terminating

