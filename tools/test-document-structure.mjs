import {test} from 'node:test';
import assert from 'node:assert/strict';
import {documentStructureErrors} from '../verify-document-structure.mjs';
const shell=(head='',body='')=>`<!doctype html><html lang="ko"><head>${head}</head><body>${body}</body></html>`;
test('ordinary static page and raw-text examples are valid',()=>{
 assert.deepEqual(documentStructureErrors(shell('<script>const x="<html><head></head></html>";</script><!-- <head> -->','<textarea><body></body></textarea><p>학생 안내</p>')),[]);
});
test('head fragments cannot create nested documents',()=>{
 assert.equal(documentStructureErrors(shell('<html><head><link href="/a.css"></head></html>')).length,1);
});
test('missing and out-of-order boundaries are rejected',()=>{
 assert.equal(documentStructureErrors('<html><body></body></html>').length,1);
 assert.equal(documentStructureErrors('<html><head><body></head></body></html>').length,1);
});
test('content containers must close in order without losing the article wrapper',()=>{
 assert.deepEqual(documentStructureErrors(shell('','<article><div><section><p>자료</p></section></div></article>')),[]);
 assert.ok(documentStructureErrors(shell('','<article><div><section></section></div></section><section></section></div></article>')).length>0);
 assert.deepEqual(documentStructureErrors(shell('','<div><script>const example="</div></section>";</script></div>')),[]);
});
