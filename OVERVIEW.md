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

done: main.py file to start backend and frontend
    + proper shutdown is ensured when terminating

