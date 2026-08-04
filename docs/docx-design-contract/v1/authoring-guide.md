# DOCX design contract v1

Create a Letter portrait document with 0.7-inch margins. Use Aptos for body text, Aptos Display for headings, and the dark-blue palette recorded in `contract.json`. Add a ruled header and a dynamic `Page X of Y` footer.

The visible document must contain, in order: Assessment Metadata; Questions; Answer Key and Step-by-Step Solutions; Assessment Quality Check; and Suggested Revision Options. Metadata, answer-key, and five-column quality information use real Word tables with pale-blue alternating rows. Each question has exactly five labeled choices and one visible correct answer in the solution section. Solutions expose every typed step from the manifest and analyze all four distractors. Use native Word equations where feasible. Embed charts as PNG images with descriptive alternative text; external links are forbidden.

Write only `/output/assessment.docx` and `/output/assessment_manifest.json`. The JSON must conform exactly to `rewritten-assessment/1` and agree with the visible DOCX.
