/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Déclenche automatiquement l'import quand la fenêtre de progression s'ouvre.
 * Protection stricte contre les doubles déclenchements.
 */
const importAutoTriggerService = {
    dependencies: ["action"],
    start(env, { action }) {
        // Garde globale : empêche tout double déclenchement dans la même session
        let alreadyTriggered = false;

        const observer = new MutationObserver((mutations) => {
            if (alreadyTriggered) return;

            for (const mutation of mutations) {
                for (const node of mutation.addedNodes) {
                    if (node.nodeType !== 1) continue;

                    // Cherche le bouton ORES ou RESA
                    const selector = 'button[name="action_do_import"]';
                    let btn = null;

                    if (node.matches?.(selector)) {
                        btn = node;
                    } else if (node.querySelector) {
                        btn = node.querySelector(selector);
                    }

                    if (btn && (btn.id === 'btn_do_import' || btn.id === 'btn_do_import_resa')) {
                        // Marque comme déjà déclenché
                        alreadyTriggered = true;
                        btn.dataset.autoClicked = "1";

                        // Délai pour laisser la fenêtre s'afficher complètement
                        setTimeout(() => {
                            if (btn.isConnected && !btn.disabled) {
                                btn.click();
                            }
                            // Réinitialise APRÈS un long délai (au cas où une nouvelle fenêtre s'ouvre)
                            setTimeout(() => { alreadyTriggered = false; }, 30000);
                        }, 300);

                        return;
                    }
                }
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
    },
};

registry.category("services").add("import_ores_resa.auto_trigger", importAutoTriggerService);