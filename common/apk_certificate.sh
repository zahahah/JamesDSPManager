#!/system/bin/sh

# Extract the first X.509 certificate from the APK's v1 PKCS#7 signature and
# return its full SHA-256. This avoids PackageManager's short 32-bit signature
# hash, which is not safe for deciding whether user data may be removed.
jdsp_der_read_tlv() {
	local file="$1"
	local offset="$2"
	JDSP_DER_START_OFFSET=$offset
	local byte
	local length_byte
	local length_octets
	local index

	byte=$(od -An -tu1 -N1 -j "$offset" "$file" 2>/dev/null | tr -d ' ')
	[ -n "$byte" ] || return 1
	JDSP_DER_TAG=$byte
	offset=$((offset + 1))
	length_byte=$(od -An -tu1 -N1 -j "$offset" "$file" 2>/dev/null | tr -d ' ')
	[ -n "$length_byte" ] || return 1
	offset=$((offset + 1))
	if [ "$length_byte" -lt 128 ]; then
		JDSP_DER_LENGTH=$length_byte
	else
		length_octets=$((length_byte - 128))
		[ "$length_octets" -gt 0 ] && [ "$length_octets" -le 4 ] || return 1
		JDSP_DER_LENGTH=0
		index=0
		while [ "$index" -lt "$length_octets" ]; do
			byte=$(od -An -tu1 -N1 -j "$offset" "$file" 2>/dev/null | tr -d ' ')
			[ -n "$byte" ] || return 1
			JDSP_DER_LENGTH=$((JDSP_DER_LENGTH * 256 + byte))
			offset=$((offset + 1))
			index=$((index + 1))
		done
	fi
	JDSP_DER_VALUE_OFFSET=$offset
	JDSP_DER_END_OFFSET=$((offset + JDSP_DER_LENGTH))
}

jdsp_apk_certificate_sha256() {
	local apk="$1"
	local signature_entry
	local workdir
	local pkcs7
	local cert
	local cert_start
	local cert_size
	local signed_data_end
	local offset
	local digest

	signature_entry=$(unzip -l "$apk" 2>/dev/null |
		awk '$4 ~ /^META-INF/ && $4 ~ /\.(RSA|DSA|EC)$/ {print $4; exit}')
	[ -n "$signature_entry" ] || return 1
	workdir="${TMPDIR:-/data/local/tmp}/jdsp-apk-cert-$$"
	mkdir -p "$workdir" || return 1
	pkcs7="$workdir/signature.der"
	cert="$workdir/certificate.der"
	if ! unzip -p "$apk" "$signature_entry" > "$pkcs7" 2>/dev/null; then
		rm -rf "$workdir"
		return 1
	fi

	jdsp_der_read_tlv "$pkcs7" 0 || { rm -rf "$workdir"; return 1; }
	[ "$JDSP_DER_TAG" -eq 48 ] || { rm -rf "$workdir"; return 1; }
	jdsp_der_read_tlv "$pkcs7" "$JDSP_DER_VALUE_OFFSET" || { rm -rf "$workdir"; return 1; }
	[ "$JDSP_DER_TAG" -eq 6 ] || { rm -rf "$workdir"; return 1; }
	jdsp_der_read_tlv "$pkcs7" "$JDSP_DER_END_OFFSET" || { rm -rf "$workdir"; return 1; }
	[ "$JDSP_DER_TAG" -eq 160 ] || { rm -rf "$workdir"; return 1; }
	jdsp_der_read_tlv "$pkcs7" "$JDSP_DER_VALUE_OFFSET" || { rm -rf "$workdir"; return 1; }
	[ "$JDSP_DER_TAG" -eq 48 ] || { rm -rf "$workdir"; return 1; }
	signed_data_end=$JDSP_DER_END_OFFSET
	offset=$JDSP_DER_VALUE_OFFSET

	while [ "$offset" -lt "$signed_data_end" ]; do
		jdsp_der_read_tlv "$pkcs7" "$offset" || { rm -rf "$workdir"; return 1; }
		if [ "$JDSP_DER_TAG" -eq 160 ]; then
			jdsp_der_read_tlv "$pkcs7" "$JDSP_DER_VALUE_OFFSET" || { rm -rf "$workdir"; return 1; }
			[ "$JDSP_DER_TAG" -eq 48 ] || { rm -rf "$workdir"; return 1; }
			cert_start=$JDSP_DER_START_OFFSET
			cert_size=$((JDSP_DER_END_OFFSET - cert_start))
			dd if="$pkcs7" of="$cert" bs=1 skip="$cert_start" count="$cert_size" 2>/dev/null || {
				rm -rf "$workdir"
				return 1
			}
			digest=$(sha256sum "$cert" 2>/dev/null | awk '{print $1}')
			rm -rf "$workdir"
			[ -n "$digest" ] || return 1
			printf '%s\n' "$digest"
			return 0
		fi
		offset=$JDSP_DER_END_OFFSET
	done
	rm -rf "$workdir"
	return 1
}
