const vscode = require('vscode');

const hoverData = {
    'This is the program': "Starts a new Veritas program. Syntax: This is the program 'name'.",
    'End of the program': "Ends a Veritas program. Syntax: End of the program 'name'.",
    'Include the': "Includes a C library or header. Syntax: Include the library 'stdio.h'.",
    'Define the function': "Begins a function definition. Syntax: Define the function 'name' with 'arg' as a type returning type.",
    'End function': "Ends a function definition. Syntax: End function 'name'.",
    'Create': "Declares a new variable or array. Syntax: Create 'name' as a type [with value val].",
    'Replace': "Assigns a value to a variable or pointer. Syntax: Replace 'name' with value.",
    'Call': "Invokes a function. Syntax: Call 'name' [with args], stored to 'dest'.",
    'For every iteration': "Starts a for loop. Syntax: For every iteration of 'i' from A through/to B.",
    'End iteration': "Ends a for loop. Syntax: End iteration of 'i' from A through/to B.",
    'If': "Conditional block. Syntax: If condition: ...",
    'Otherwise': "Else block. Syntax: Otherwise: ...",
    'End if': "Ends a conditional block. Syntax: End if condition.",
    'the quantity': "Groups expressions for precedence. Syntax: the quantity expr [; multiplied by ...]",
    'stored to': "Specifies the return destination for a Call statement.",
    'returning': "Specifies the return type of a function.",
    'nothing': "The Veritas equivalent of 'void'."
};

function activate(context) {
    const hoverEntries = Object.entries(hoverData)
        .sort((a, b) => b[0].length - a[0].length);

    let hoverProvider = vscode.languages.registerHoverProvider('veritas', {
        provideHover(document, position, token) {
            const line = document.lineAt(position.line).text;
            const cursor = position.character;

            for (const [keyword, helpText] of hoverEntries) {
                const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                const pattern = new RegExp(`\\b${escaped}\\b`, 'g');
                let match;
                while ((match = pattern.exec(line)) !== null) {
                    const start = match.index;
                    const end = start + keyword.length;
                    if (cursor >= start && cursor <= end) {
                        const range = new vscode.Range(position.line, start, position.line, end);
                        return new vscode.Hover(helpText, range);
                    }
                }
            }

            return undefined;
        }
    });

    context.subscriptions.push(hoverProvider);
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};
