import {createPublicKey,verify} from 'node:crypto';
import {readFileSync} from 'node:fs';

try {
 const {key,manifest,signature}=JSON.parse(readFileSync(0,'utf8'));
 const publicKey=createPublicKey(key);
 const signed=Buffer.from(signature,'base64');
 if(publicKey.asymmetricKeyType!=='ed25519'||signed.length!==64||
    !verify(null,Buffer.from(manifest,'base64'),publicKey,signed))process.exitCode=1;
} catch {process.exitCode=1}
